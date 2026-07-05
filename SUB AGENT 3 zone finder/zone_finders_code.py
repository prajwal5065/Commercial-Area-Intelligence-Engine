"""
zone_finders_code.py  —  SUB-AGENT 3: ZONE FINDER (production)
================================================================
Two-pass architecture:
  Pass 1 — Discover zone names  (Tavily → LLM)
  Pass 2 — Count businesses per zone  (Tavily → regex → LLM extract → LLM estimate)

Count strategy (three layers, first hit wins):
  Layer 1 — Regex:    extract numbers directly from Tavily content
  Layer 2 — LLM:      let LLM read same content and find a number
  Layer 3 — Estimate: ask LLM to estimate from its own knowledge

Results are persisted to the zones table in Supabase via upsert.

Switch LLM:  change ACTIVE_PROVIDER below to "groq", "gemini", or "openai"

.env keys required:
    SUPABASE_URL, SUPABASE_KEY
    TAVILY_API_KEY
    GROQ_API_KEY        (if ACTIVE_PROVIDER = "groq")
    GEMINI_API_KEY      (if ACTIVE_PROVIDER = "gemini")
    OPENAI_API_KEY      (if ACTIVE_PROVIDER = "openai")
"""
import os
import re
import json
import sys
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

import time
from rate_limiter import tavily_limiter, groq_limiter  # ADD THIS LINE

from supabase_client import upsert_zone

load_dotenv()

# --------------------------------------------------
# Cooperative stop signal (optional)
# --------------------------------------------------
# A threading.Event can be registered via set_stop_event() so long retry
# loops in call_llm()/tavily_search() can bail out between attempts when the
# user hits Stop, instead of always exhausting all RETRY_ATTEMPTS. Not
# required for normal operation - if never set, behaves exactly as before.
_STOP_EVENT = None


def set_stop_event(event) -> None:
    """Register a threading.Event to check between retry attempts."""
    global _STOP_EVENT
    _STOP_EVENT = event


def _stop_requested() -> bool:
    return _STOP_EVENT is not None and _STOP_EVENT.is_set()


# --------------------------------------------------
# Logging
# --------------------------------------------------

# Reconfigure stdout/stderr to prevent UnicodeEncodeErrors on Windows CP1252/etc.
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass

try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(stream=sys.stdout)
        ]
    )
    for _h in logging.root.handlers:
        if hasattr(_h, 'stream') and hasattr(_h.stream, 'reconfigure'):
            try:
                _h.stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
except Exception:
    pass

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  ★  SWITCH YOUR LLM HERE  ★
# ═══════════════════════════════════════════════════════════════════
ACTIVE_PROVIDER = "groq"   # "groq" | "gemini" | "openai"


# ── Provider registry ─────────────────────────────────────────────
PROVIDERS = {
    "groq": {
        "api_key_env":  "GROQ_API_KEY",
        "api_url":      "https://api.groq.com/openai/v1/chat/completions",
        "model":        "llama-3.3-70b-versatile",
        "max_out_tok":  2000,
        "tpm_limit":    6_000,
        "request_fmt":  "openai",
    },
    "gemini": {
        "api_key_env":  "GEMINI_API_KEY",
        "api_url":      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model":        "gemini-2.0-flash",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "gemini",
    },
    "openai": {
        "api_key_env":  "OPENAI_API_KEY",
        "api_url":      "https://api.openai.com/v1/chat/completions",
        "model":        "gpt-4o-mini",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "openai",
    },
}

TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY")
TAVILY_API_URL  = "https://api.tavily.com/search"

RETRY_ATTEMPTS  = 5
RETRY_DELAY_SEC = 5

if ACTIVE_PROVIDER not in PROVIDERS:
    log.error(f"Unknown provider '{ACTIVE_PROVIDER}'. Choose: {list(PROVIDERS)}")
    sys.exit(1)

P               = PROVIDERS[ACTIVE_PROVIDER]
LLM_API_KEY     = os.getenv(P["api_key_env"])
LLM_MODEL       = P["model"]
LLM_MAX_OUT_TOK = P["max_out_tok"]
LLM_API_URL     = P["api_url"]
LLM_FMT         = P["request_fmt"]
LLM_TPM_LIMIT   = P["tpm_limit"]

_OVERHEAD_TOK = 700
if LLM_TPM_LIMIT:
    LLM_MAX_CONTEXT_CHARS = max((LLM_TPM_LIMIT - LLM_MAX_OUT_TOK - _OVERHEAD_TOK) * 4, 2000)
else:
    LLM_MAX_CONTEXT_CHARS = 60_000


# ═══════════════════════════════════════════════════════════════════
#  REGEX COUNT EXTRACTION
# ═══════════════════════════════════════════════════════════════════

COUNT_PATTERNS = [
    (r'(\d[\d,]+)\s*(?:businesses|companies|suppliers|firms|units|tenants|results|listings)\s*(?:found|listed|in|for|matching)',
     "directory_total"),
    (r'(?:houses?|home to|hosts?)\s+(?:over|more than|approximately|nearly|around|about)?\s*(\d[\d,]+)\s*(?:companies|businesses|firms|units|tenants|MSMEs|IT)',
     "authority_page"),
    (r'(?:more than|over|approximately|nearly|around|about)\s+(\d[\d,]+)\s*(?:companies|businesses|firms|units|tenants|MSMEs|IT firms|suppliers)',
     "authority_page"),
    (r'(\d[\d,]+)\+\s*(?:companies|businesses|firms|units|tenants|MSMEs|IT)',
     "directory_listing"),
    (r'(\d[\d,]+)\s*(?:companies|businesses|firms|units|tenants|MSMEs)\s*(?:are|were|operate|registered|set up|located)',
     "authority_page"),
    (r'(?:has|have|with)\s+(\d[\d,]+)\s*(?:registered|listed)?\s*(?:companies|businesses|units|firms|tenants)',
     "authority_page"),
    (r'(\d[\d,]+)\s*(?:companies|businesses|firms|IT companies|units)',
     "generic"),
]


def regex_extract_count(text: str):
    for pattern, source_type in COUNT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            num = int(m.group(1).replace(",", ""))
            if num > 0:
                return num, source_type
    return None


def extract_best_count_from_results(results: list):
    priority = {
        "directory_total":   0,
        "authority_page":    1,
        "directory_listing": 2,
        "generic":           3,
    }
    best = None
    for r in results:
        text = (r.get("content") or "") + " " + (r.get("title") or "")
        hit  = regex_extract_count(text)
        if hit:
            count, src = hit
            p = priority.get(src, 9)
            if best is None or p < best[0]:
                best = (p, count, src, r.get("url", ""))
    if best:
        return best[1], best[2], best[3]
    return None


# ═══════════════════════════════════════════════════════════════════
#  TAVILY
# ═══════════════════════════════════════════════════════════════════

# Module-level flag — set to False the first time a plan-limit error is hit.
TAVILY_AVAILABLE = True


def tavily_search(query: str, max_results: int = 7) -> list:
    global TAVILY_AVAILABLE

    if not TAVILY_AVAILABLE or not TAVILY_API_KEY:
        return []

    payload = {
        "api_key":             TAVILY_API_KEY,
        "query":               query,
        "search_depth":        "advanced",
        "max_results":         max_results,
        "include_answer":      True,
        "include_raw_content": False,
    }
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.post(TAVILY_API_URL, json=payload, timeout=30)
            err_str = str(resp.status_code)
            if resp.status_code in (429, 432):
                log.warning(f"Tavily plan/rate limit hit (HTTP {resp.status_code}) — disabling Tavily for this run.")
                TAVILY_AVAILABLE = False
                return []
            resp.raise_for_status()
            data    = resp.json()
            results = data.get("results", [])
            if data.get("answer"):
                results.append({
                    "title":   "Tavily answer",
                    "url":     "tavily-answer",
                    "content": data["answer"],
                })
            return results
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["432", "429", "rate limit", "rate_limit", "quota", "credits", "too many requests"]):
                log.warning(f"Tavily plan/rate limit error — disabling Tavily for this run: {e}")
                TAVILY_AVAILABLE = False
                return []
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)
            else:
                log.warning(f"Tavily failed after {RETRY_ATTEMPTS} attempts: {e}")
                return []


def results_to_context(results: list, chars_per: int = 500) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"[{i}] {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"{(r.get('content') or '')[:chars_per]}"
        )
    return "\n---\n".join(parts)


def trim_to_budget(ctx: str) -> str:
    if len(ctx) <= LLM_MAX_CONTEXT_CHARS:
        return ctx
    cut = ctx[:LLM_MAX_CONTEXT_CHARS]
    sep = cut.rfind("\n---\n")
    return cut[:sep] if sep > 0 else cut


# ═══════════════════════════════════════════════════════════════════
#  LLM  (provider-agnostic, with retry and 413 trim)
# ═══════════════════════════════════════════════════════════════════

def _openai_payload(system, user):
    return {
        "model":       LLM_MODEL,
        "temperature": 0.1,
        "max_tokens":  LLM_MAX_OUT_TOK,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }


def _gemini_payload(system, user):
    return {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": LLM_MAX_OUT_TOK},
    }


def _openai_extract(rj):
    c = rj["choices"][0]
    return c["message"]["content"], c.get("finish_reason", "")


def _gemini_extract(rj):
    c = rj["candidates"][0]
    return c["content"]["parts"][0]["text"], c.get("finishReason", "")


def call_llm(system: str, user: str) -> str:
    """
    Call the active LLM provider.
    Retries on 429 / 500 / 502 / 503.
    Trims context and retries on 413.
    Raises RuntimeError after all attempts exhausted.
    """
    cur_user = user

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        if _stop_requested():
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] Stop requested — aborting retry loop.")
            raise RuntimeError("Stopped by user request.")
        if ACTIVE_PROVIDER == "groq" and 'groq_limiter' in globals():
            groq_limiter.wait()
        if LLM_FMT == "openai":
            payload = _openai_payload(system, cur_user)
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {LLM_API_KEY}",
            }
            url = LLM_API_URL
        else:
            payload = _gemini_payload(system, cur_user)
            headers = {"Content-Type": "application/json"}
            url = f"{LLM_API_URL}?key={LLM_API_KEY}"

        est = (len(system) + len(cur_user)) // 4
        log.info(f"[{ACTIVE_PROVIDER.upper()}] attempt {attempt} (~{est:,} tok)")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.exceptions.Timeout:
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] Timeout on attempt {attempt}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue
            raise
        except requests.exceptions.ConnectionError as ce:
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] Connection error on attempt {attempt}: {ce}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue
            raise

        if resp.status_code == 413:
            try:
                err = resp.json().get("error", {}).get("message", "")
            except Exception:
                err = resp.text
            lm  = re.search(r"Limit\s+(\d+)", err)
            rm  = re.search(r"Requested\s+(\d+)", err)
            cut = ((int(rm.group(1)) - int(lm.group(1)) + 100) * 4) if lm and rm else len(cur_user) // 2
            if attempt < RETRY_ATTEMPTS:
                cur_user = cur_user[:-cut] if cut < len(cur_user) else cur_user[:2000]
                log.warning(f"[{ACTIVE_PROVIDER.upper()}] 413 — trimmed context, retrying...")
                continue
            raise RuntimeError("413 persists. Raise tpm_limit or switch ACTIVE_PROVIDER.")

        if resp.status_code == 429:
            # Parse retry-after header (Groq returns a future Unix timestamp)
            wait = 65  # Safe default
            retry_after = resp.headers.get("retry-after")
            if retry_after:
                try:
                    ra_val = float(retry_after)
                    # If > 1e9, it's a Unix timestamp, not relative seconds
                    if ra_val > 1e9:
                        wait = int(ra_val - time.time()) + 2
                    else:
                        wait = int(ra_val) + 2
                except (ValueError, TypeError):
                    pass
            
            # # Cap maximum wait to 120 seconds to avoid absurd delays
            # wait = max(5, min(wait, 120))
            # Honor the exact wait time from the API header
            if wait < 2:
                wait = 2  # Minimum 2 seconds to be safe

            log.warning(
                f"[{ACTIVE_PROVIDER.upper()}] 429 rate limit — "
                f"waiting {wait}s (attempt {attempt}/{RETRY_ATTEMPTS})"
            )
            if attempt < RETRY_ATTEMPTS:
                # Sleep in short chunks so a stop request doesn't have to wait
                # out the full 429 backoff (which can be 65s+) before taking effect.
                remaining = wait
                while remaining > 0:
                    if _stop_requested():
                        log.warning(f"[{ACTIVE_PROVIDER.upper()}] Stop requested during 429 backoff — aborting.")
                        raise RuntimeError("Stopped by user request.")
                    chunk = min(2, remaining)
                    time.sleep(chunk)
                    remaining -= chunk
                continue

        if resp.status_code in (500, 502, 503):
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] HTTP {resp.status_code} — retrying...")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)
                continue

        resp.raise_for_status()
        rj = resp.json()
        content, finish = (_openai_extract if LLM_FMT == "openai" else _gemini_extract)(rj)
        if finish in ("length", "MAX_TOKENS"):
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] Output truncated at token limit")
        log.info(f"[{ACTIVE_PROVIDER.upper()}] OK — {len(content)} chars returned")
        return content

    raise RuntimeError(f"LLM call failed after {RETRY_ATTEMPTS} attempts.")


# ═══════════════════════════════════════════════════════════════════
#  JSON HELPERS
# ═══════════════════════════════════════════════════════════════════

def extract_json_obj(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e != -1:
        t = t[s:e + 1]
    elif s != -1:
        t = t[s:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # attempt bracket repair
    t = re.sub(r',\s*$', '', t.rstrip())
    stack, in_s, esc = [], False, False
    for ch in t:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_s = not in_s
        if not in_s:
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']') and stack:
                stack.pop()
    return json.loads(t + ''.join(reversed(stack)))


def extract_json_array(raw: str) -> list:
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = t.find("["), t.rfind("]")
    if s != -1 and e != -1:
        t = t[s:e + 1]
    try:
        result = json.loads(t)
        if not isinstance(result, list):
            raise ValueError(f"Expected list, got {type(result)}")
        return result
    except Exception as exc:
        raise ValueError(f"Failed to parse JSON array: {exc}\nRaw: {raw[:300]}")


# ═══════════════════════════════════════════════════════════════════
#  PASS 1 — Discover zone names
# ═══════════════════════════════════════════════════════════════════

PASS1_SYSTEM = """
You are a commercial zone analyst.
Given web search results about a city, list ALL significant commercial zones:
IT parks, industrial estates, CBDs, SEZs, market districts, trade clusters.
Output ONLY a raw JSON array of zone name strings. No other text.
Example: ["Hinjewadi IT Park","Magarpatta City","Pune Camp","Kothrud"]
"""


PASS1_LLM_ONLY_SYSTEM = """
You are a commercial zone analyst with comprehensive knowledge of cities worldwide.
Given a city and country name, list ALL significant commercial zones from your training knowledge:
IT parks, industrial estates, CBDs, SEZs, market districts, trade clusters, tech hubs.
Output ONLY a raw JSON array of zone name strings. No other text.
Example: ["Hinjewadi IT Park","Magarpatta City","Pune Camp","Kothrud"]
Be thorough — list at least 8-15 zones if they exist.
"""


def discover_zones(city: str, country: str) -> list:
    global TAVILY_AVAILABLE
    log.info(f"[Pass 1] Discovering zones for {city}, {country}")

    # LLM-only path: Tavily unavailable or not configured
    if not TAVILY_AVAILABLE or not TAVILY_API_KEY:
        log.info(f"[Pass 1] Tavily unavailable — using LLM-only zone discovery for {city}")
        try:
            raw = call_llm(
                PASS1_LLM_ONLY_SYSTEM,
                f"City: {city}, Country: {country}\n\n"
                f"List all significant commercial zones, business districts, IT parks, SEZs, "
                f"industrial estates, and market areas in {city}. "
                f"Output ONLY a JSON array of zone name strings.",
            )
            zones = extract_json_array(raw)
            zones = [z for z in zones if isinstance(z, str) and z.strip()]
            log.info(f"[Pass 1-LLM] {city}: {len(zones)} zones discovered (LLM-only)")
            return zones
        except Exception as e:
            log.error(f"[Pass 1-LLM] {city}: LLM-only zone discovery failed — {e}")
            return []

    results, seen = [], set()
    tavily_limiter.wait()
    try:
        for r in tavily_search(
            f"{city} {country} IT parks SEZ industrial estates commercial zones business districts trade clusters list",
            max_results=7
        ):
            if r.get("url", "") not in seen:
                seen.add(r.get("url", ""))
                results.append(r)
    except Exception as e:
        log.warning(f"[Pass 1] Tavily error for {city}: {e}")

    # If Tavily returned nothing, fall back to LLM-only
    if not results:
        log.info(f"[Pass 1] No Tavily results for {city} — falling back to LLM-only")
        try:
            raw = call_llm(
                PASS1_LLM_ONLY_SYSTEM,
                f"City: {city}, Country: {country}\n\n"
                f"List all significant commercial zones, business districts, IT parks, SEZs, "
                f"industrial estates, and market areas in {city}. "
                f"Output ONLY a JSON array of zone name strings.",
            )
            zones = extract_json_array(raw)
            zones = [z for z in zones if isinstance(z, str) and z.strip()]
            log.info(f"[Pass 1-LLM] {city}: {len(zones)} zones discovered (LLM-only fallback)")
            return zones
        except Exception as e:
            log.error(f"[Pass 1-LLM] {city}: LLM fallback failed — {e}")
            return []

    ctx = trim_to_budget(results_to_context(results, chars_per=400))
    raw = call_llm(
        PASS1_SYSTEM,
        f"City: {city}, Country: {country}\n\nSearch results:\n{ctx}\n\n"
        f"Output ONLY a JSON array of zone name strings.",
    )

    try:
        zones = extract_json_array(raw)
        zones = [z for z in zones if isinstance(z, str) and z.strip()]
        log.info(f"[Pass 1] {city}: {len(zones)} zones discovered")
        return zones
    except Exception as e:
        log.error(f"[Pass 1] {city}: failed to parse zone list — {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  PASS 2 — Count businesses per zone (3-layer strategy)
# ═══════════════════════════════════════════════════════════════════

PASS2_EXTRACT_SYSTEM = """
You are a business count extractor.
Given web search results for a specific commercial zone, find the number
of businesses/companies/tenants in that zone.

Look for: "X companies", "X businesses", "X units", "houses X firms",
"X results found", directory listing totals, registered unit counts.

Output ONLY: {"business_count": <integer>, "count_source": "<source>", "source_url": "<url>"}
If you find a number use it.
If you cannot find any number output: {"business_count": null, "count_source": "not_found", "source_url": ""}
"""

PASS2_ESTIMATE_SYSTEM = """
You are a business density expert for cities worldwide.
Given a commercial zone name and city, estimate how many businesses operate there.

Base your estimate on:
- Zone type (IT park vs market vs industrial estate vs CBD)
- Zone size if mentioned
- Typical densities for similar zones in cities of that country

Output ONLY: {"business_count": <integer>, "count_source": "Estimated", "source_url": ""}
Always provide a number. Never return null.
"""


def fetch_zone_count(zone_name: str, city: str, country: str) -> dict:
    """
    Three-layer count strategy for one zone.
    Layer 1 — Regex on Tavily content    (fast, no LLM tokens consumed)
    Layer 2 — LLM reads Tavily content   (catches what regex misses)
    Layer 3 — LLM estimates from knowledge (guaranteed non-null fallback)
    """
    # If Tavily is unavailable, skip straight to Layer 3 (LLM estimate)
    if not TAVILY_AVAILABLE or not TAVILY_API_KEY:
        log.info(f"  [L1/L2 skipped] Tavily unavailable for {zone_name} — going straight to LLM estimate")
        results = []
    else:
        results, seen = [], set()
        for q in [
            f'"{zone_name}" {city} number of companies businesses',
            f'"{zone_name}" {city} businesses listed directory',
            f'"{zone_name}" {city} total units tenants registered firms',
        ]:
            if 'tavily_limiter' in globals():
                tavily_limiter.wait()
            else:
                time.sleep(1)
            for r in tavily_search(q, max_results=5):
                if r.get("url", "") not in seen:
                    seen.add(r.get("url", ""))
                    results.append(r)

    # Layer 1: Regex
    hit = extract_best_count_from_results(results)
    if hit:
        count, src, url = hit
        log.info(f"  [L1-Regex] {zone_name}: {count:,} [{src}]")
        return {"business_count": count, "count_source": src, "source_url": url}

    log.info(f"  [L1-Regex] {zone_name}: no match — trying LLM extraction")

    # Layer 2: LLM extraction from search content
    if results:
        ctx = results_to_context(results[:6], chars_per=400)
        ctx = trim_to_budget(ctx)
        try:
            raw = call_llm(
                PASS2_EXTRACT_SYSTEM,
                f"Zone: {zone_name}\nCity: {city}, Country: {country}\n\n"
                f"Search results:\n{ctx}\n\n"
                f"Find the business count. Output ONLY the JSON object.",
            )
            result = extract_json_obj(raw)
            bc = result.get("business_count")
            if bc is not None:
                result["business_count"] = int(round(float(bc)))
                log.info(f"  [L2-LLM] {zone_name}: {result['business_count']:,} [{result.get('count_source')}]")
                return result
        except Exception as e:
            log.warning(f"  [L2-LLM] {zone_name}: parse error — {e}")
    else:
        log.info(f"  [L2-LLM] {zone_name}: skipped (no search results returned)")

    # Layer 3: LLM estimate
    log.info(f"  [L3-Est] {zone_name}: requesting LLM estimate")
    try:
        raw = call_llm(
            PASS2_ESTIMATE_SYSTEM,
            f"Zone: {zone_name}\nCity: {city}, Country: {country}\n\n"
            f"Estimate the number of businesses in this zone. Output ONLY the JSON object.",
        )
        result = extract_json_obj(raw)
        bc = result.get("business_count")
        if bc is not None:
            result["business_count"] = int(round(float(bc)))
            log.info(f"  [L3-Est] {zone_name}: {result['business_count']:,} [Estimated]")
            return result
    except Exception as e:
        log.warning(f"  [L3-Est] {zone_name}: parse error — {e}")

    log.warning(f"  [Fallback] {zone_name}: all layers failed — defaulting to 0")
    return {"business_count": 0, "count_source": "unknown", "source_url": ""}


# ═══════════════════════════════════════════════════════════════════
#  ASSEMBLE RESULTS
# ═══════════════════════════════════════════════════════════════════

def assemble_results(city: str, country: str, zones: list, counts: list) -> dict:
    records = []
    for zone_name, cd in zip(zones, counts):
        records.append({
            "zone_name":      zone_name,
            "business_count": cd.get("business_count"),
            "count_source":   cd.get("count_source", ""),
            "source_url":     cd.get("source_url", ""),
            "city":           city,
            "country":        country,
        })
    counted = sorted(
        [r for r in records if r["business_count"] is not None],
        key=lambda r: r["business_count"],
        reverse=True,
    )
    nulls = [r for r in records if r["business_count"] is None]
    final = counted + nulls
    for i, r in enumerate(final, 1):
        r["rank"] = i
    return {
        "status":       "SUCCESS",
        "city":         city,
        "country":      country,
        "provider":     f"{ACTIVE_PROVIDER}/{LLM_MODEL}",
        "retrieved_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "zones":        final,
    }


# ═══════════════════════════════════════════════════════════════════
#  PERSIST TO SUPABASE
# ═══════════════════════════════════════════════════════════════════

def save_zones_to_supabase(city: str, country: str, zones: list) -> int:
    saved = 0
    for zone in zones:
        zone_name = zone.get("zone_name", "").strip()
        if not zone_name:
            continue
        try:
            upsert_zone(
                zone_name=zone_name,
                city_name=city,
                country_name=country,
                business_count=zone.get("business_count"),
                count_source=zone.get("count_source", ""),
                source_url=zone.get("source_url", ""),
                rank=zone.get("rank"),
            )
            saved += 1
        except Exception as e:
            log.error(f"Failed to save zone '{zone_name}' ({city}): {e}")
    return saved


# ═══════════════════════════════════════════════════════════════════
#  SAVE JSON SNAPSHOT
# ═══════════════════════════════════════════════════════════════════

def save_json_snapshot(data: dict, city: str) -> str:
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_city = re.sub(r"[^\w]", "_", city.lower())
    fname     = f"zones_{safe_city}_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return fname


# ═══════════════════════════════════════════════════════════════════
#  LOG SUMMARY TABLE
# ═══════════════════════════════════════════════════════════════════

def log_results(data: dict) -> None:
    zones   = data.get("zones", [])
    counted = [z for z in zones if z.get("business_count") is not None]
    nulls   = [z for z in zones if z.get("business_count") is None]
    div     = "=" * 65
    log.info(div)
    log.info(f"  ZONE FINDER — {data.get('city', '').upper()}, {data.get('country', '').upper()}")
    log.info(div)
    log.info(f"  Provider : {data.get('provider')}")
    log.info(f"  Zones    : {len(zones)}  (counted={len(counted)}, estimated/null={len(nulls)})")
    log.info(f"  At       : {data.get('retrieved_at')}")
    for z in zones:
        bc   = z.get("business_count")
        src  = z.get("count_source", "")
        flag = "~" if src in ("Estimated", "unknown") else " "
        log.info(
            f"  #{z['rank']:>2} {flag} {z['zone_name']:<35} "
            f"{str(bc) if bc is not None else 'NULL':>7}  [{src}]"
        )
    log.info(div)


# ═══════════════════════════════════════════════════════════════════
#  MAIN PIPELINE — process one city
# ═══════════════════════════════════════════════════════════════════

def process_city(city: str, country: str, stop_event=None) -> dict:
    """
    Full pipeline for one city:
      1. Discover zones (Pass 1)
      2. Count businesses per zone (Pass 2, 3-layer)
      3. Assemble ranked results
      4. Persist to Supabase via upsert
      5. Save local JSON snapshot

    Never raises. Returns a status dict so swarm workers continue on failure.

    stop_event: optional threading.Event, registered with this module so
    call_llm()/tavily_search() retry loops can check it and bail out early
    instead of exhausting all retry attempts when the user requests a stop.
    """
    if stop_event is not None:
        set_stop_event(stop_event)
    log.info(f"Processing: {city}, {country}")

    # Pass 1 — zone discovery
    try:
        zones = discover_zones(city, country)
    except Exception as e:
        log.error(f"{city}: zone discovery failed — {e}")
        return {"status": "FAILED", "city": city, "country": country, "zones": []}

    if stop_event is not None and stop_event.is_set():
        log.warning(f"{city}: stop requested after zone discovery — skipping zone counting.")
        return {"status": "STOPPED", "city": city, "country": country, "zones": []}

    if not zones:
        log.warning(f"{city}: no zones discovered, skipping")
        return {"status": "NO_ZONES", "city": city, "country": country, "zones": []}

    # Pass 2 — count businesses per zone
    counts = []
    for zone in zones:
        if stop_event is not None and stop_event.is_set():
            log.warning(f"{city}: stop requested — halting zone counting early.")
            break
        try:
            counts.append(fetch_zone_count(zone, city, country))
        except Exception as e:
            log.error(f"{city} / {zone}: count fetch failed — {e}")
            counts.append({"business_count": 0, "count_source": "error", "source_url": ""})

    # Assemble
    data = assemble_results(city, country, zones, counts)

    # Persist to Supabase
    try:
        saved = save_zones_to_supabase(city, country, data["zones"])
        log.info(f"{city}: {saved}/{len(data['zones'])} zones saved to Supabase")
    except Exception as e:
        log.error(f"{city}: Supabase persistence error — {e}")

    # Save local snapshot
    try:
        fname = save_json_snapshot(data, city)
        log.info(f"{city}: snapshot saved → {fname}")
    except Exception as e:
        log.warning(f"{city}: could not write JSON snapshot — {e}")

    log_results(data)
    log.info(f"Completed: {city}")
    return data


# ═══════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) == 3:
        city    = sys.argv[1].strip()
        country = sys.argv[2].strip()
    elif len(sys.argv) == 2:
        city    = sys.argv[1].strip()
        country = input("Country: ").strip()
    else:
        city    = input("City: ").strip()
        country = input("Country: ").strip()

    if not city or not country:
        log.error("City and country are required.")
        sys.exit(1)

    missing = []
    if not LLM_API_KEY:
        missing.append(P["api_key_env"])
    if missing:
        log.error(f"Missing in .env: {', '.join(missing)}")
        sys.exit(1)

    if not TAVILY_API_KEY:
        log.warning("TAVILY_API_KEY not set — running Agent 3 in LLM-only mode.")

    process_city(city, country)

if __name__ == "__main__":
    main()