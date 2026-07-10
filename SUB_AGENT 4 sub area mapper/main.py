import json
import os
import re
import sys
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import load_dotenv
from config import GEMINI_MODEL

# Adaptive concurrency health tracking (soft import — works without the file)
try:
    import sys
    _PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _PROJ not in sys.path:
        sys.path.insert(0, _PROJ)
    from adaptive_concurrency import get_provider_manager as _get_provider_manager
    from adaptive_concurrency import record_outcome as _record_outcome
except ImportError:
    def _get_provider_manager(p): return type('dummy', (), {'sem': type('s', (), {'acquire_blocking': lambda: None, 'release': lambda: None})()})
    def _record_outcome(*args, **kwargs): pass

try:
    from rate_limiter import gemini_limiter
except ImportError:
    class NoOpLimiter:
        def wait(self): pass
    gemini_limiter = NoOpLimiter()

# ── Load .env: first try the sub-agent's own folder, then walk up to find
# the project root .env so Supabase/Groq keys are always available when
# this module is imported from a worker thread in run_pipeline.py.
_HERE_MAIN = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE_MAIN, ".env"))          # sub-agent .env (if any)
# Walk up directory tree looking for the project root .env
_search = _HERE_MAIN
for _ in range(5):
    _candidate = os.path.join(_search, ".env")
    if os.path.exists(_candidate):
        load_dotenv(_candidate, override=False)          # project root .env
    _search = os.path.dirname(_search)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# --------------------------------------------------
# Rate-limit reporting callback (optional)
# --------------------------------------------------
# Same pattern as SUB AGENT 2/city_segmenters_code.py and
# SUB AGENT 3 zone finder/zone_finders_code.py. No-op if never set.
_RATE_LIMIT_CALLBACK = None


def set_rate_limit_callback(fn) -> None:
    """Register a callback: fn(provider: str, detail: str) -> None, called
    whenever this module detects a 429/rate-limit on a provider."""
    global _RATE_LIMIT_CALLBACK
    _RATE_LIMIT_CALLBACK = fn


def _report_rate_limit(provider: str, detail: str = "") -> None:
    if _RATE_LIMIT_CALLBACK is not None:
        try:
            _RATE_LIMIT_CALLBACK(provider, detail)
        except Exception:
            pass  # never let a reporting hook break the actual pipeline run

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    log.warning("[main.py] GROQ_API_KEY not found in .env — process_zone calls will fail.")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create Supabase client only when credentials are available.
# Missing credentials are non-fatal: subareas are still written to disk;
# only Supabase insertion is skipped.
_supabase_available = bool(SUPABASE_URL and SUPABASE_KEY)
if not _supabase_available:
    log.warning("[main.py] SUPABASE_URL or SUPABASE_KEY missing — Supabase insertion disabled.")
    supabase = None
else:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as _e:
        log.warning(f"[main.py] Could not create Supabase client: {_e} — insertion disabled.")
        supabase = None
        _supabase_available = False

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Provider registry (all 10 LLMs matching the frontend selector) ──────────
# key = provider string the frontend sends.  Falls back to "groq" if an
# unknown key or missing env var is passed.
PROVIDERS = {
    # ── Groq (fast, free-tier) ──────────────────────────────────────
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "api_url":     "https://api.groq.com/openai/v1/chat/completions",
        "model":       "llama-3.3-70b-versatile",
        "request_fmt": "openai",
    },
    "groq-llama-70b": {
        "api_key_env": "GROQ_API_KEY",
        "api_url":     "https://api.groq.com/openai/v1/chat/completions",
        "model":       "llama-3.1-70b-versatile",
        "request_fmt": "openai",
    },
    "groq-llama-8b": {
        "api_key_env": "GROQ_API_KEY",
        "api_url":     "https://api.groq.com/openai/v1/chat/completions",
        "model":       "llama-3.1-8b-instant",
        "request_fmt": "openai",
    },
    "groq-mixtral": {
        "api_key_env": "GROQ_API_KEY",
        "api_url":     "https://api.groq.com/openai/v1/chat/completions",
        "model":       "mixtral-8x7b-32768",
        "request_fmt": "openai",
    },
    # ── Google Gemini ────────────────────────────────────────────────
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "api_url":     f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        "model":       GEMINI_MODEL,
        "request_fmt": "gemini",
    },
    "gemini-pro": {
        "api_key_env": "GEMINI_API_KEY",
        "api_url":     f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        "model":       GEMINI_MODEL,
        "request_fmt": "gemini",
    },
    # ── OpenAI ───────────────────────────────────────────────────────
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "api_url":     "https://api.openai.com/v1/chat/completions",
        "model":       "gpt-4o-mini",
        "request_fmt": "openai",
    },
    "gpt-4o": {
        "api_key_env": "OPENAI_API_KEY",
        "api_url":     "https://api.openai.com/v1/chat/completions",
        "model":       "gpt-4o",
        "request_fmt": "openai",
    },
    # ── Anthropic Claude ─────────────────────────────────────────────
    "claude": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_url":     "https://api.anthropic.com/v1/messages",
        "model":       "claude-3-haiku-20240307",
        "request_fmt": "anthropic",
    },
    # ── Mistral ──────────────────────────────────────────────────────
    "mistral": {
        "api_key_env": "MISTRAL_API_KEY",
        "api_url":     "https://api.mistral.ai/v1/chat/completions",
        "model":       "mistral-7b-instruct",
        "request_fmt": "openai",
    },
}

DEFAULT_PROVIDER = "groq"




def _gemini_payload(prompt: str) -> dict:
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8000},
    }


def _openai_payload(prompt: str, model: str) -> dict:
    return {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }


def _anthropic_payload(prompt: str, model: str) -> dict:
    """Anthropic Messages API payload (claude-3-*)."""
    return {
        "model": model,
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }


def call_groq(prompt: str, provider: str = DEFAULT_PROVIDER) -> str:
    """Call the chosen LLM provider. Name kept as call_groq for backward
    compatibility with any existing callers that don't pass a provider -
    defaults to Groq, identical behavior to before this function supported
    provider choice.

    provider: one of PROVIDERS' keys ("groq" | "gemini" | "openai"). Falls
    back to Groq with a warning if an unknown or unconfigured provider name
    is given, rather than raising - a bad provider choice shouldn't crash a
    whole zone's mapping when Groq would have worked.
    """
    if provider not in PROVIDERS:
        log.warning(f"[main.py] Unknown provider '{provider}', falling back to '{DEFAULT_PROVIDER}'.")
        provider = DEFAULT_PROVIDER

    cfg = PROVIDERS[provider]
    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        log.warning(
            f"[main.py] {cfg['api_key_env']} not set for provider '{provider}' — "
            f"falling back to '{DEFAULT_PROVIDER}'."
        )
        provider = DEFAULT_PROVIDER
        cfg = PROVIDERS[provider]
        api_key = os.getenv(cfg["api_key_env"])

    if cfg["request_fmt"] == "gemini":
        payload = _gemini_payload(prompt)
        headers = {"Content-Type": "application/json"}
        url = f"{cfg['api_url']}?key={api_key}"
    elif cfg["request_fmt"] == "anthropic":
        payload = _anthropic_payload(prompt, cfg["model"])
        headers = {
            "Content-Type":         "application/json",
            "x-api-key":            api_key,
            "anthropic-version":    "2023-06-01",
        }
        url = cfg["api_url"]
    else:
        payload = _openai_payload(prompt, cfg["model"])
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        url = cfg["api_url"]

    if provider.startswith("gemini"):
        gemini_limiter.wait()

    _t0 = time.time()
    try:
        t_start = datetime.now().isoformat()
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        t_end = datetime.now().isoformat()
        
        if cfg["request_fmt"] == "gemini":
            log.info(
                "\n=====================================\n"
                f"Worker ID              : Agent4 Worker\n"
                f"Country                : Unknown\n"
                f"Selected Provider      : {provider}\n"
                f"Gemini Model           : {cfg['model']}\n"
                f"API Request Started    : {t_start}\n"
                f"API Request Completed  : {t_end}\n"
                f"HTTP Status            : {resp.status_code}\n"
                "====================================="
            )
        _latency = time.time() - _t0
        is_429 = resp.status_code == 429
        if is_429:
            log.warning(f"[main.py] [{provider.upper()}] HTTP 429 Rate Limit. Full error: {resp.text}")
            _record_outcome(provider, success=False, is_429=True, is_timeout=False, latency=_latency)
        resp.raise_for_status()
        rj = resp.json()
        _record_outcome(provider, success=True, is_429=False, is_timeout=False, latency=_latency)
        if cfg["request_fmt"] == "gemini":
            return rj["candidates"][0]["content"]["parts"][0]["text"]
        if cfg["request_fmt"] == "anthropic":
            return rj["content"][0]["text"]
        return rj["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        _record_outcome(provider, success=False, is_429=False, is_timeout=True, latency=time.time() - _t0)
        raise
    except Exception:
        _record_outcome(provider, success=False, is_429=False, is_timeout=False, latency=time.time() - _t0)
        raise

REQUIRED_KEYS = {"status", "agent", "input", "results", "supporting_sources"}


def sanitize_filename(name: str) -> str:
    """Remove illegal filename characters and replace spaces with underscores."""
    safe = re.sub(r'[\\/*?:"<>|]', "", name)
    return safe.replace(" ", "_")


def validate_response(data: dict) -> bool:
    """Check if the parsed JSON contains all required top-level keys."""
    if not isinstance(data, dict):
        return False
    return REQUIRED_KEYS.issubset(data.keys())


def extract_json(raw: str) -> Optional[dict]:
    """Strip markdown fences and extract JSON object from raw string."""
    content = raw.strip()
    if content.startswith("```"):
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        content = content.strip()
    
    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            return None
    return None


def insert_subareas_to_supabase(data: dict) -> Dict[str, int]:
    """Extract results from validated JSON and insert into Supabase."""
    if not _supabase_available or supabase is None:
        log.info("[main.py] Supabase unavailable — skipping DB insertion.")
        return {"inserted": 0, "skipped": 0, "failed": 0}

    if not isinstance(data, dict) or "input" not in data or "results" not in data:
        return {"inserted": 0, "skipped": 0, "failed": 0}

    zone_name = data["input"].get("zone_name", "Unknown")
    country = data["input"].get("country", "Unknown")

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    for item in data["results"]:
        row = {
            "zone_name": zone_name,
            "subarea_name": item.get("subarea_name"),
            "parent_zone": item.get("parent_zone"),
            "business_volume": item.get("business_volume"),
            "city": item.get("city"),
            "country": country,
            "source_url": item.get("source_url"),
            "retrieved_at": item.get("retrieved_at"),
            "status": item.get("status")
        }

        try:
            supabase.table("subareas").insert(row).execute()
            inserted_count += 1
            log.info(f"Supabase inserted: {row['subarea_name']}")
        except Exception as e:
            err_str = str(e)
            if "23505" in err_str or "duplicate" in err_str.lower():
                log.warning(f"Supabase skipped duplicate: {row['subarea_name']}")
                skipped_count += 1
            else:
                log.error(f"Supabase failed to insert {row['subarea_name']}: {e}")
                failed_count += 1

    log.info(f"Supabase sync for {zone_name}: Inserted={inserted_count}, Skipped={skipped_count}, Failed={failed_count}")
    return {"inserted": inserted_count, "skipped": skipped_count, "failed": failed_count}


def process_zone(zone_name: str, city: str, country: str, provider: str = DEFAULT_PROVIDER) -> Dict[str, Any]:
    """Execute the sub-area mapping pipeline for a single zone.

    provider: which LLM to use for this call ("groq" | "gemini" | "openai").
    Manual choice only - set by the caller (phase_4_subarea_mapper), not
    auto-selected. Defaults to Groq, matching prior behavior exactly when
    no provider is specified.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "prompt.txt")
    output_dir = os.path.join(current_dir, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    try:
        log.info(f"Loading prompt from {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as file:
            prompt_template = file.read()
    except Exception as e:
        log.error(f"Failed to load prompt: {e}")
        return {"status": "ERROR", "zone": zone_name, "path": None}

    final_prompt = prompt_template.format(
        zone_name=zone_name,
        city=city,
        country=country
    )

    providers_to_try = [provider]
    if provider == "groq":
        providers_to_try.extend(["gemini", "openai"])
    elif provider == "gemini":
        providers_to_try.extend(["groq", "openai"])
    elif provider == "openai":
        providers_to_try.extend(["groq", "gemini"])

    max_attempts = 3
    raw_response = None

    for current_provider in providers_to_try:
        log.info(f"Trying provider: {current_provider} for {zone_name}")
        for attempt in range(1, max_attempts + 1):
            try:
                log.info(f"Sending request for {zone_name} via {current_provider} (attempt {attempt}/{max_attempts})")
                raw_response = call_groq(final_prompt, provider=current_provider)
                
                # Hollow response check
                if not raw_response or not raw_response.strip():
                    raise Exception("Hollow response: empty string")
                temp_parsed = extract_json(raw_response)
                if temp_parsed and isinstance(temp_parsed, dict) and validate_response(temp_parsed):
                    if not temp_parsed.get("results"):
                        raise Exception("Hollow response: 0 results returned")
                
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str or "timeout" in err_str or "network" in err_str or "connection" in err_str or "resolve" in err_str or "hollow response" in err_str:
                    import random
                    wait_sec = (2 ** attempt) + random.uniform(0, 1)

                    if "429" in err_str or "rate_limit" in err_str:
                        _report_rate_limit(current_provider, f"zone={zone_name}, attempt={attempt}")
                        
                        if hasattr(e, 'response') and e.response is not None:
                            try:
                                err_json = e.response.json()
                                if "error" in err_json and "retryDelay" in err_json["error"]:
                                    wait_sec = float(err_json["error"]["retryDelay"][:-1]) + 2
                            except Exception:
                                pass

                            retry_after = e.response.headers.get("retry-after")
                            if retry_after:
                                try:
                                    ra_val = float(retry_after)
                                    if ra_val > 1e9:
                                        wait_sec = int(ra_val - time.time()) + 2
                                    else:
                                        wait_sec = int(ra_val) + 2
                                except (ValueError, TypeError):
                                    pass
                                    
                    if wait_sec < 2:
                        wait_sec = 2

                    log.warning(f"{zone_name} [{current_provider}]: Retryable error on attempt {attempt}. Waiting {wait_sec:.1f}s. Error: {e}")
                    if attempt < max_attempts:
                        time.sleep(wait_sec)
                    else:
                        log.error(f"{zone_name} [{current_provider}]: All {max_attempts} attempts failed.")

                else:
                    log.error(f"{zone_name} [{current_provider}]: Non-retryable error: {e}")
                    break  # try next provider
        if raw_response and not "Hollow response" in str(raw_response):
            # Also break if we succeeded with non-hollow
            # Actually, if we get here and raw_response is set and didn't raise Exception, we are good.
            break

    if not raw_response:
        log.error(f"{zone_name}: All providers failed.")
        return {"status": "ERROR", "zone": zone_name, "path": None}

    parsed_data = None
    for parse_attempt in range(2):
        parsed_data = extract_json(raw_response)
        if parsed_data and validate_response(parsed_data):
            break
        else:
            log.warning(f"{zone_name}: Invalid JSON or missing keys (validation attempt {parse_attempt + 1}/2)")
            if parse_attempt == 1:
                log.error(f"{zone_name}: Validation failed twice. Saving raw response.")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_zone = sanitize_filename(zone_name)
                raw_filename = f"raw_{safe_zone}_{timestamp}.json"
                raw_path = os.path.join(output_dir, raw_filename)
                try:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(raw_response)
                    log.info(f"Saved raw response to {raw_path}")
                except Exception as e:
                    log.error(f"Failed to save raw response: {e}")
                return {"status": "ERROR", "zone": zone_name, "path": raw_path}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_zone = sanitize_filename(zone_name)
    filename = f"{safe_zone}_{timestamp}.json"
    output_path = os.path.join(output_dir, filename)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=2, ensure_ascii=False)
        log.info(f"Saved output to {output_path}")
    except Exception as e:
        log.error(f"Failed to save output file: {e}")
        return {"status": "ERROR", "zone": zone_name, "path": None}

    # Automatically insert into Supabase
    db_summary = {"inserted": 0, "skipped": 0, "failed": 0}
    try:
        log.info(f"Starting automatic Supabase insertion for {zone_name}")
        db_summary = insert_subareas_to_supabase(parsed_data)
    except Exception as e:
        log.error(f"Critical error during Supabase insertion: {e}")

    return {
        "status": "SUCCESS", 
        "zone": zone_name, 
        "path": output_path,
        "db_inserted": db_summary.get("inserted", 0),
        "db_skipped": db_summary.get("skipped", 0),
        "db_failed": db_summary.get("failed", 0)
    }


if __name__ == "__main__":
    zone_name = input("Enter zone name: ").strip()
    city = input("Enter city: ").strip()
    country = input("Enter country: ").strip()

    if not zone_name or not city or not country:
        log.error("Zone name, city, and country are required.")
    else:
        result = process_zone(zone_name, city, country)
        log.info(f"Finished processing. Final status: {result['status']}")