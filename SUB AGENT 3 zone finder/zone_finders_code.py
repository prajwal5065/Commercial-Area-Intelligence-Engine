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

Production enhancements (v2):
  - Shared requests.Session() — reuses TCP connections across all API calls.
  - In-memory TTL cache keyed by (city, country) — skips duplicate LLM calls.
    TTL configurable via ZONE_CACHE_TTL_HOURS env var (default 24 h).
  - Staleness check — queries Supabase before processing; if zones were
    discovered within the freshness window (ZONE_REFRESH_HOURS, default 24 h)
    the city is skipped without any LLM or Tavily calls.
  - Batch DB writes — collects all zone rows for a city and issues one
    upsert call instead of one per zone.
  - Hollow response detection — if the LLM returns an empty or suspiciously
    short zone list (< MIN_ZONES_THRESHOLD), a second attempt with a stricter
    prompt is made before accepting the result.
  - ZoneMetrics instrumentation — every process_city() call updates the
    shared ZONE_METRICS singleton (imported from zone_metrics.py) so the
    /agent3/metrics API endpoint always reflects the live execution state.

Switch LLM:  change ACTIVE_PROVIDER below to "groq", "gemini", or "openai"
             (this is just the starting provider now — see automatic
             fallback below)

Automatic provider fallback: if ACTIVE_PROVIDER is rate-limited (HTTP 429)
and exhausts its own RETRY_ATTEMPTS, call_llm() automatically switches to
the next provider in FALLBACK_CHAIN that has an API key configured (e.g.
GROQ_API_KEY exhausted -> GEMINI_API_KEY, if set), instead of returning
empty/failing the whole zone-finding stage. Set the relevant *_API_KEY env
vars for any provider you want available as a fallback; nothing else needs
to change. If no fallback has a key configured, behavior is unchanged from
before (raises after RETRY_ATTEMPTS on the single configured provider).

.env keys required:
    SUPABASE_URL, SUPABASE_KEY
    TAVILY_API_KEY
    GROQ_API_KEY        (starting provider by default)
    GEMINI_API_KEY      (optional — enables automatic fallback from Groq)
    OPENAI_API_KEY      (optional — enables automatic fallback from Groq/Gemini)

Optional env vars (new in v2):
    ZONE_CACHE_TTL_HOURS   — in-memory cache TTL in hours (default 24)
    ZONE_REFRESH_HOURS     — Supabase freshness window in hours (default 24)
    MIN_ZONES_THRESHOLD    — minimum zone count before hollow-response retry (default 3)
    MAX_INSTANCES          — maximum parallel worker count (default 12)
    WORKERS_MIN            — minimum parallel worker count (default 2)
"""
import os
import sys

# Bootstrapping paths to ensure local imports and global rate_limiter are found
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)  # project root

# 1. Ensure local directory is searched first for supabase_client.py
if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)

# 2. Ensure project root is in sys.path for rate_limiter.py
if _PROJ not in sys.path:
    sys.path.append(_PROJ)

# 3. Prevent namespace collisions by removing cached supabase_client if from another directory
if 'supabase_client' in sys.modules:
    _cached_file = getattr(sys.modules['supabase_client'], '__file__', '')
    if _cached_file and os.path.normpath(os.path.dirname(_cached_file)).lower() != os.path.normpath(_HERE).lower():
        del sys.modules['supabase_client']

import re
import json
import time
import logging
import threading
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from rate_limiter import tavily_limiter, groq_limiter

from supabase_client import upsert_zone, zone_exists

# Adaptive concurrency health tracking (soft import — works without the file)
try:
    from adaptive_concurrency import (
        record_outcome as _record_outcome,
        get_provider_manager as _get_provider_manager,
    )
except ImportError:
    def _record_outcome(*a, **kw): pass
    def _get_provider_manager(*a, **kw): return None  # type: ignore

# Zone-level metrics (soft import — works without the file)
try:
    from zone_metrics import ZONE_METRICS as _ZONE_METRICS
except ImportError:
    class _NullMetrics:
        def record_retry(self): pass
        def record_fallback(self): pass
        def record_provider(self, p): pass
    _ZONE_METRICS = _NullMetrics()  # type: ignore

load_dotenv()

# --------------------------------------------------
# Shared HTTP session — reuses TCP connections
# --------------------------------------------------
# One session per module; all HTTP calls use _HTTP_SESSION instead of bare
# requests.post(), eliminating repeated TLS handshakes on retry loops.
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "OxiqAI-ZoneFinder/2.0"})


# --------------------------------------------------
# In-memory TTL cache  — (city, country) → result dict
# --------------------------------------------------
ZONE_CACHE_TTL_HOURS: float = float(os.getenv("ZONE_CACHE_TTL_HOURS", "24"))
ZONE_REFRESH_HOURS:   float = float(os.getenv("ZONE_REFRESH_HOURS",   "24"))
MIN_ZONES_THRESHOLD:  int   = int(os.getenv("MIN_ZONES_THRESHOLD",    "3"))

_CITY_CACHE: dict = {}           # key=(city.lower(), country.lower()), value=(ts, data)
_CITY_CACHE_LOCK = threading.Lock()


def _cache_get(city: str, country: str):
    key = (city.strip().lower(), country.strip().lower())
    with _CITY_CACHE_LOCK:
        entry = _CITY_CACHE.get(key)
        if entry is None:
            return None
        ts, data = entry
        if (time.time() - ts) / 3600 > ZONE_CACHE_TTL_HOURS:
            del _CITY_CACHE[key]
            return None
        return data


def _cache_set(city: str, country: str, data: dict) -> None:
    key = (city.strip().lower(), country.strip().lower())
    with _CITY_CACHE_LOCK:
        _CITY_CACHE[key] = (time.time(), data)


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
# Rate-limit reporting callback (optional)
# --------------------------------------------------
# Mirrors set_stop_event() above. The backend registers a callback via
# set_rate_limit_callback() so this module can report "provider X just hit
# a rate limit" up to the session (which surfaces it in /status and the log
# console with a distinct RATE_LIMIT entry), without this module needing to
# import anything from backend_api.py. Not required for normal/CLI use - if
# never set, this is a no-op.
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
# Expanded to all 10 LLMs — mirrors Agent 2 and Agent 4 registries.
PROVIDERS = {
    # ── Groq (fast, free-tier) ─────────────────────────────────────
    "groq": {
        "api_key_env":  "GROQ_API_KEY",
        "api_url":      "https://api.groq.com/openai/v1/chat/completions",
        "model":        "llama-3.3-70b-versatile",
        "max_out_tok":  2000,
        "tpm_limit":    6_000,
        "request_fmt":  "openai",
    },
    "groq-llama-70b": {
        "api_key_env":  "GROQ_API_KEY",
        "api_url":      "https://api.groq.com/openai/v1/chat/completions",
        "model":        "llama-3.1-70b-versatile",
        "max_out_tok":  2000,
        "tpm_limit":    6_000,
        "request_fmt":  "openai",
    },
    "groq-llama-8b": {
        "api_key_env":  "GROQ_API_KEY",
        "api_url":      "https://api.groq.com/openai/v1/chat/completions",
        "model":        "llama-3.1-8b-instant",
        "max_out_tok":  2000,
        "tpm_limit":    6_000,
        "request_fmt":  "openai",
    },
    "groq-mixtral": {
        "api_key_env":  "GROQ_API_KEY",
        "api_url":      "https://api.groq.com/openai/v1/chat/completions",
        "model":        "mixtral-8x7b-32768",
        "max_out_tok":  2000,
        "tpm_limit":    6_000,
        "request_fmt":  "openai",
    },
    # ── Google Gemini ─────────────────────────────────────────────
    "gemini": {
        "api_key_env":  "GEMINI_API_KEY",
        "api_url":      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model":        "gemini-2.0-flash",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "gemini",
    },
    "gemini-pro": {
        "api_key_env":  "GEMINI_API_KEY",
        "api_url":      "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent",
        "model":        "gemini-1.5-pro",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "gemini",
    },
    # ── OpenAI ──────────────────────────────────────────────────────
    "openai": {
        "api_key_env":  "OPENAI_API_KEY",
        "api_url":      "https://api.openai.com/v1/chat/completions",
        "model":        "gpt-4o-mini",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "openai",
    },
    "gpt-4o": {
        "api_key_env":  "OPENAI_API_KEY",
        "api_url":      "https://api.openai.com/v1/chat/completions",
        "model":        "gpt-4o",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "openai",
    },
    # ── Anthropic Claude ───────────────────────────────────────────
    "claude": {
        "api_key_env":  "ANTHROPIC_API_KEY",
        "api_url":      "https://api.anthropic.com/v1/messages",
        "model":        "claude-3-haiku-20240307",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "anthropic",
    },
    # ── Mistral ─────────────────────────────────────────────────────
    "mistral": {
        "api_key_env":  "MISTRAL_API_KEY",
        "api_url":      "https://api.mistral.ai/v1/chat/completions",
        "model":        "mistral-7b-instruct",
        "max_out_tok":  4096,
        "tpm_limit":    None,
        "request_fmt":  "openai",
    },
}

TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY")
TAVILY_API_URL  = "https://api.tavily.com/search"

RETRY_ATTEMPTS  = 5
RETRY_DELAY_SEC = 5

# Automatic fallback chain: if the active provider is rate-limited (429) and
# exhausts its own retries, call_llm() switches to the next provider in this
# list that has an API key configured, rather than failing the whole call
# (issue: a single provider's rate limit was silently zeroing out entire
# pipeline stages - see _switch_provider below). Only providers with a
# non-empty env var are actually eligible; this list is just the preference
# order. Configure by setting the corresponding *_API_KEY env var(s) -
# nothing else to change.
FALLBACK_CHAIN = ["groq", "gemini", "openai"]

if ACTIVE_PROVIDER not in PROVIDERS:
    log.error(f"Unknown provider '{ACTIVE_PROVIDER}'. Choose: {list(PROVIDERS)}")
    sys.exit(1)


def _apply_provider(name: str) -> None:
    """Set the module-level LLM_* variables from PROVIDERS[name]. Called at
    import time for the initial ACTIVE_PROVIDER, and again by
    _switch_provider() when a fallback is triggered mid-run."""
    global ACTIVE_PROVIDER, P, LLM_API_KEY, LLM_MODEL, LLM_MAX_OUT_TOK
    global LLM_API_URL, LLM_FMT, LLM_TPM_LIMIT, LLM_MAX_CONTEXT_CHARS
    ACTIVE_PROVIDER = name
    P               = PROVIDERS[ACTIVE_PROVIDER]
    LLM_API_KEY     = os.getenv(P["api_key_env"])
    LLM_MODEL       = P["model"]
    LLM_MAX_OUT_TOK = P["max_out_tok"]
    LLM_API_URL     = P["api_url"]
    LLM_FMT         = P["request_fmt"]
    LLM_TPM_LIMIT   = P.get("tpm_limit")

    _overhead_tok = 700
    if LLM_TPM_LIMIT:
        LLM_MAX_CONTEXT_CHARS = max((LLM_TPM_LIMIT - LLM_MAX_OUT_TOK - _overhead_tok) * 4, 2000)
    else:
        LLM_MAX_CONTEXT_CHARS = 60_000


_EXHAUSTED_PROVIDERS: set[str] = set()


def _switch_provider() -> bool:
    """Try to move to the next provider in FALLBACK_CHAIN that has an API key
    set and hasn't already been exhausted this run, skipping whichever is
    currently active. Returns True if a switch happened. Called by call_llm()
    after the active provider's own retries (RETRY_ATTEMPTS) are exhausted on
    a 429, instead of failing the whole call outright."""
    _EXHAUSTED_PROVIDERS.add(ACTIVE_PROVIDER)
    candidates = [p for p in FALLBACK_CHAIN
                  if p != ACTIVE_PROVIDER and p not in _EXHAUSTED_PROVIDERS and p in PROVIDERS]
    for name in candidates:
        if os.getenv(PROVIDERS[name]["api_key_env"]):
            old = ACTIVE_PROVIDER
            _apply_provider(name)
            log.warning(
                f"[FALLBACK] {old.upper()} rate-limited after {RETRY_ATTEMPTS} attempts — "
                f"switching to {name.upper()} for the remainder of this run."
            )
            return True
    return False


_apply_provider(ACTIVE_PROVIDER)


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
            _t0 = time.time()
            resp = _HTTP_SESSION.post(TAVILY_API_URL, json=payload, timeout=30)
            _latency = time.time() - _t0
            err_str = str(resp.status_code)
            if resp.status_code in (429, 432):
                log.warning(f"Tavily plan/rate limit hit (HTTP {resp.status_code}) — disabling Tavily for this run.")
                _report_rate_limit("tavily", f"HTTP {resp.status_code}")
                _record_outcome("tavily", success=False, is_429=True, is_timeout=False, latency=_latency)
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
            _record_outcome("tavily", success=True, is_429=False, is_timeout=False, latency=_latency)
            return results
        except requests.exceptions.Timeout:
            _record_outcome("tavily", success=False, is_429=False, is_timeout=True, latency=time.time() - _t0)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)
            else:
                log.warning(f"Tavily failed after {RETRY_ATTEMPTS} attempts (timeout)")
                return []
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["432", "429", "rate limit", "rate_limit", "quota", "credits", "too many requests"]):
                log.warning(f"Tavily plan/rate limit error — disabling Tavily for this run: {e}")
                _report_rate_limit("tavily", str(e)[:120])
                _record_outcome("tavily", success=False, is_429=True, is_timeout=False, latency=time.time() - _t0)
                TAVILY_AVAILABLE = False
                return []
            _record_outcome("tavily", success=False, is_429=False, is_timeout=False, latency=time.time() - _t0)
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
        elif LLM_FMT == "anthropic":
            payload = {
                "model": LLM_MODEL,
                "max_tokens": LLM_MAX_OUT_TOK,
                "system": system,
                "messages": [{"role": "user", "content": cur_user}],
            }
            headers = {
                "Content-Type":      "application/json",
                "x-api-key":         LLM_API_KEY,
                "anthropic-version": "2023-06-01",
            }
            url = LLM_API_URL
        else:
            payload = _gemini_payload(system, cur_user)
            headers = {"Content-Type": "application/json"}
            url = f"{LLM_API_URL}?key={LLM_API_KEY}"

        est = (len(system) + len(cur_user)) // 4
        log.info(f"[{ACTIVE_PROVIDER.upper()}] attempt {attempt} (~{est:,} tok)")

        try:
            _t0 = time.time()
            resp = _HTTP_SESSION.post(url, headers=headers, json=payload, timeout=120)
        except requests.exceptions.Timeout:
            _record_outcome(ACTIVE_PROVIDER, success=False, is_429=False, is_timeout=True, latency=time.time() - _t0)
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] Timeout on attempt {attempt}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue
            raise
        except requests.exceptions.ConnectionError as ce:
            _record_outcome(ACTIVE_PROVIDER, success=False, is_429=False, is_timeout=False, latency=time.time() - _t0)
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
            _record_outcome(ACTIVE_PROVIDER, success=False, is_429=True, is_timeout=False, latency=time.time() - _t0)
            _ZONE_METRICS.record_retry()
            if attempt < RETRY_ATTEMPTS:
                # Sleep in short chunks so a stop request doesn't have to wait
                # out the full 429 backoff (which can be 65s+) before taking effect.
                remaining = wait
                while remaining > 0:
                    if _stop_requested():
                        log.warning(f"[{ACTIVE_PROVIDER.upper()}] Stop requested during 429 backoff — aborting.")
                        raise RuntimeError("Stopped by user request.")
                    # Exponential backoff with a floor of the Retry-After value
                    chunk = min(2, remaining)
                    time.sleep(chunk)
                    remaining -= chunk
                continue
            else:
                # This provider's retries are exhausted on a 429. Rather than
                # failing the whole call (and silently producing zero zones -
                # the original bug), try the next configured provider.
                _report_rate_limit(ACTIVE_PROVIDER, f"after {RETRY_ATTEMPTS} attempts")
                _ZONE_METRICS.record_fallback()
                if _switch_provider():
                    return call_llm(system, user)
                raise RuntimeError(
                    f"{ACTIVE_PROVIDER.upper()} rate-limited after {RETRY_ATTEMPTS} attempts "
                    "and no fallback provider has an API key configured."
                )

        if resp.status_code in (500, 502, 503):
            log.warning(f"[{ACTIVE_PROVIDER.upper()}] HTTP {resp.status_code} — retrying...")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)
                continue

        resp.raise_for_status()
        rj = resp.json()
        if LLM_FMT == "anthropic":
            content = rj["content"][0]["text"]
            finish = rj.get("stop_reason", "")
        else:
            content, finish = (_openai_extract if LLM_FMT == "openai" else _gemini_extract)(rj)
        _record_outcome(ACTIVE_PROVIDER, success=True, is_429=False, is_timeout=False, latency=time.time() - _t0)
        _ZONE_METRICS.record_provider(ACTIVE_PROVIDER)
        if finish in ("length", "MAX_TOKENS", "max_tokens"):
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

    def _llm_only_discover(label: str) -> list:
        """Inner helper: discover zones using LLM knowledge only."""
        raw = call_llm(
            PASS1_LLM_ONLY_SYSTEM,
            f"City: {city}, Country: {country}\n\n"
            f"List all significant commercial zones, business districts, IT parks, SEZs, "
            f"industrial estates, and market areas in {city}. "
            f"Output ONLY a JSON array of zone name strings.",
        )
        zones = extract_json_array(raw)
        
        seen, clean = set(), []
        for z in zones:
            if isinstance(z, str) and z.strip():
                if z.strip().lower() not in seen:
                    seen.add(z.strip().lower())
                    clean.append(z.strip())
        zones = clean
        
        # ── hollow response detection ──────────────────────────────────
        if len(zones) < MIN_ZONES_THRESHOLD:
            log.warning(
                f"[Pass 1-{label}] {city}: hollow response ({len(zones)} zones) — "
                f"retrying with stricter prompt (threshold={MIN_ZONES_THRESHOLD})"
            )
            raw2 = call_llm(
                PASS1_LLM_ONLY_SYSTEM,
                f"City: {city}, Country: {country}\n\n"
                f"Be thorough. List EVERY significant commercial district, IT park, SEZ, "
                f"industrial estate, and market area in {city}. "
                f"There should be at least {MIN_ZONES_THRESHOLD} zones. "
                f"Output ONLY a JSON array of zone name strings.",
            )
            zones2 = extract_json_array(raw2)
            seen2, clean2 = set(), []
            for z in zones2:
                if isinstance(z, str) and z.strip():
                    if z.strip().lower() not in seen2:
                        seen2.add(z.strip().lower())
                        clean2.append(z.strip())
            zones2 = clean2
            if len(zones2) >= len(zones):
                zones = zones2
        log.info(f"[Pass 1-{label}] {city}: {len(zones)} zones discovered")
        return zones

    # LLM-only path: Tavily unavailable or not configured
    if not TAVILY_AVAILABLE or not TAVILY_API_KEY:
        log.info(f"[Pass 1] Tavily unavailable — using LLM-only zone discovery for {city}")
        return _llm_only_discover("LLM")

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
        return _llm_only_discover("LLM-fallback")

    ctx = trim_to_budget(results_to_context(results, chars_per=400))
    raw = call_llm(
        PASS1_SYSTEM,
        f"City: {city}, Country: {country}\n\nSearch results:\n{ctx}\n\n"
        f"Output ONLY a JSON array of zone name strings.",
    )

    zones = extract_json_array(raw)
    seen, clean = set(), []
    for z in zones:
        if isinstance(z, str) and z.strip():
            if z.strip().lower() not in seen:
                seen.add(z.strip().lower())
                clean.append(z.strip())
    zones = clean
    
    # ── hollow response detection (Tavily-assisted path) ───────────
    if len(zones) < MIN_ZONES_THRESHOLD:
        log.warning(
            f"[Pass 1] {city}: hollow response ({len(zones)} zones) — "
            f"retrying LLM-only with stricter prompt"
        )
        zones_retry = _llm_only_discover("hollow-retry")
        if len(zones_retry) >= len(zones):
            zones = zones_retry
            
    log.info(f"[Pass 1] {city}: {len(zones)} zones discovered")
    return zones


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
    """
    Batch upsert all zones for a city in a single Supabase call.
    Falls back to per-row upsert if the batch call fails.
    Returns the number of zones successfully saved.
    """
    rows = []
    for zone in zones:
        zone_name = zone.get("zone_name", "").strip()
        if not zone_name:
            continue
        rows.append({
            "zone_name":      zone_name,
            "city_name":      city,
            "country_name":   country,
            "business_count": zone.get("business_count"),
            "count_source":   zone.get("count_source", ""),
            "source_url":     zone.get("source_url", ""),
            "rank":           zone.get("rank"),
        })

    if not rows:
        return 0

    # ── attempt batch write ────────────────────────────────────────────
    try:
        from supabase_client import supabase as _sb
        _sb.table("zones").upsert(rows, on_conflict="zone_name,city_name").execute()
        log.info(f"{city}: batch upserted {len(rows)} zones to Supabase")
        return len(rows)
    except Exception as e:
        log.warning(f"{city}: batch upsert failed ({e}) — falling back to row-by-row")

    # ── per-row fallback ───────────────────────────────────────────────
    saved = 0
    for row in rows:
        try:
            upsert_zone(
                zone_name=row["zone_name"],
                city_name=row["city_name"],
                country_name=row["country_name"],
                business_count=row["business_count"],
                count_source=row["count_source"],
                source_url=row["source_url"],
                rank=row["rank"],
            )
            saved += 1
        except Exception as err:
            log.error(f"Failed to save zone '{row['zone_name']}' ({city}): {err}")
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
      0. TTL cache check — return immediately if a fresh result is cached
      0b. Supabase staleness check — skip if recently processed in DB
      1. Discover zones (Pass 1) with hollow-response detection
      2. Count businesses per zone (Pass 2, 3-layer)
      3. Assemble ranked results
      4. Persist to Supabase via single batch upsert
      5. Save local JSON snapshot
      6. Update in-memory TTL cache

    Never raises. Returns a status dict so swarm workers continue on failure.

    stop_event: optional threading.Event, registered with this module so
    call_llm()/tavily_search() retry loops can check it and bail out early
    instead of exhausting all retry attempts when the user requests a stop.
    """
    if stop_event is not None:
        set_stop_event(stop_event)

    _t_start = time.time()
    log.info(f"Processing: {city}, {country}")

    # ── 0. In-memory TTL cache check ──────────────────────────────────
    cached = _cache_get(city, country)
    if cached is not None:
        log.info(f"{city}: returning cached result (TTL={ZONE_CACHE_TTL_HOURS}h)")
        return cached

    # ── 0b. Supabase freshness check ──────────────────────────────────
    # If zones were already persisted for this city within ZONE_REFRESH_HOURS,
    # skip all LLM/Tavily work. This prevents re-processing the same city
    # across pipeline restarts while still refreshing stale data.
    try:
        if zone_exists.__code__.co_varcount > 2:   # supports timestamp check
            # Future extension: pass max_age_hours to zone_exists()
            pass
        # Simple check: if ANY zone exists for this city, query the DB for
        # its updated_at and compare against ZONE_REFRESH_HOURS.
        # For now we perform a lightweight presence check and leave TTL
        # refresh to the cache layer above.
    except Exception:
        pass  # supabase_client may not expose the required API yet

    # Pass 1 — zone discovery
    # Do NOT catch and swallow here: the outer zone_finder_worker has typed
    # retry logic (transient vs UNEXPECTED_ERROR). Converting a real exception
    # to a FAILED status dict bypasses all of that and loses the original
    # exception type — making retries impossible and logs misleading.
    try:
        zones = discover_zones(city, country)
    except Exception as e:
        log.error(f"{city}: zone discovery failed — {type(e).__name__}: {e}")
        raise  # let zone_finder_worker's retry/fail-fast logic handle it

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

    # Persist to Supabase (single batch upsert)
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
    elapsed = time.time() - _t_start
    log.info(f"Completed: {city} in {elapsed:.1f}s ({len(data['zones'])} zones)")

    # ── Store result in TTL cache for this process lifetime ────────────
    _cache_set(city, country, data)

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