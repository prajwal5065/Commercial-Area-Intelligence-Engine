"""
adaptive_concurrency.py — Adaptive Concurrency Manager with Provider Health Scoring
=====================================================================================
Reusable across Agent 2, 3, 4, and 5.

Key features
------------
* Per-provider health score (0–1) updated via Exponential Moving Average (EMA).
  health = EMA_ALPHA × previous_health + (1 – EMA_ALPHA) × latest_sample

* Health score is a configurable weighted composite of four signals:
    success_rate  (W_SUCCESS  default 0.40)
    429-rate      (W_429      default 0.30, inverted)
    timeout-rate  (W_TIMEOUT  default 0.20, inverted)
    latency       (W_LATENCY  default 0.10, inverted, normalised against the
                  provider's own rolling baseline latency so naturally slow
                  providers are not penalised vs naturally fast ones)

* Sliding window: metrics are computed over the last N requests only
  (default WINDOW_SIZE = 50), preventing distant history from masking
  current degradation.

* Concurrency driven by score thresholds:
    score < SCORE_DECREASE_THRESHOLD  → step down aggressively (fast)
    score > SCORE_INCREASE_THRESHOLD  → step up slowly (additive)

* Custom ResizableSemaphore — already-running tasks keep their permit;
  only *new* acquisitions see the updated limit (asyncio.Semaphore can't
  be resized natively).

* Concurrency floor: never drops below WORKERS_MIN.

* One manager instance per provider (completely independent health tracking).

* Exposes a rich to_dict() snapshot consumed by the /provider-health API
  endpoint — includes success_rate, rate_429, timeout_rate, avg_latency,
  status label, retry_count, fallback_count, and current model.

* Detailed logging on every concurrency change: provider, old→new,
  health score, all metric rates, latency ratio, and human-readable reason.

Usage
-----
  from adaptive_concurrency import get_provider_manager, record_outcome

  mgr = get_provider_manager("groq")

  # Acquire permit before submitting a task:
  mgr.sem.acquire_blocking()
  start = time.time()
  try:
      result = call_llm(...)
      record_outcome("groq", success=True, is_429=False,
                     is_timeout=False, latency=time.time()-start)
  except RateLimitError:
      record_outcome("groq", success=False, is_429=True,
                     is_timeout=False, latency=time.time()-start)
      raise
  finally:
      mgr.sem.release()
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Configurable constants (all override-able via env)
# ─────────────────────────────────────────────

MAX_INSTANCES: int = int(os.getenv("MAX_INSTANCES", "12"))
WORKERS_MIN:   int = int(os.getenv("WORKERS_MIN",   "2"))

# Workers removed per aggressive decrease / added per gradual increase
STEP_DOWN: int = int(os.getenv("CONCURRENCY_STEP_DOWN", "2"))
STEP_UP:   int = int(os.getenv("CONCURRENCY_STEP_UP",   "1"))

# Health score thresholds
SCORE_DECREASE_THRESHOLD: float = float(os.getenv("SCORE_DECREASE_THRESHOLD", "0.70"))
SCORE_INCREASE_THRESHOLD: float = float(os.getenv("SCORE_INCREASE_THRESHOLD", "0.90"))

# EMA smoothing factor (higher = slower adaptation / more inertia)
EMA_ALPHA: float = float(os.getenv("HEALTH_EMA_ALPHA", "0.80"))

# Composite score weights (should sum to 1.0)
W_SUCCESS: float = float(os.getenv("W_SUCCESS", "0.40"))
W_429:     float = float(os.getenv("W_429",     "0.30"))
W_TIMEOUT: float = float(os.getenv("W_TIMEOUT", "0.20"))
W_LATENCY: float = float(os.getenv("W_LATENCY", "0.10"))

# Sliding window size — metrics computed over last N API calls only
WINDOW_SIZE: int = int(os.getenv("HEALTH_WINDOW_SIZE", "50"))

# Minimum calls in the window before score influences concurrency
MIN_SAMPLES_BEFORE_ADJUST: int = int(os.getenv("MIN_SAMPLES_BEFORE_ADJUST", "5"))

# Hysteresis: minimum seconds between two consecutive concurrency adjustments
ADJUSTMENT_COOLDOWN_SEC: float = float(os.getenv("ADJUSTMENT_COOLDOWN_SEC", "10.0"))

# ── Proactive probe configuration ─────────────────────────────────────────────
# TTL for the cached probe result: probe is re-fired at most once per this many
# seconds. Set to 0 to disable probing entirely.
PROBE_CACHE_TTL_SEC: float = float(os.getenv("PROBE_CACHE_TTL_SEC", "60.0"))

# Per-provider minimal probe definitions.
# Each probe fires one HTTP POST/GET with a 1-token payload and records the
# outcome directly into the provider's existing record_outcome() path.
# Add an entry here for any provider that needs proactive health seeding.
# Keys must match the provider keys in PROVIDERS dicts in city_segmenters_code.py.
# Probes are intentionally tiny (1 token, 10s timeout) to consume minimal quota.
PROVIDER_PROBES: Dict[str, dict] = {
    "groq": {
        "url":     "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
        "auth":    "bearer",
        "payload": {
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Hi"}],
        },
        "success_codes": {200},
    },
    "gemini": {
        "url_template": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        "env_key":      "GEMINI_API_KEY",
        "model":        "gemini-2.0-flash",
        "auth":         "query",   # key is embedded in URL
        "payload": {
            "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
        "success_codes": {200},
    },
    "gemini-pro": {
        "url_template": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        "env_key":      "GEMINI_API_KEY",
        "model":        "gemini-2.0-flash-lite",
        "auth":         "query",
        "payload": {
            "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
        "success_codes": {200},
    },
}


# ─────────────────────────────────────────────
# Resizable semaphore
# ─────────────────────────────────────────────

class ResizableSemaphore:
    """
    A threading semaphore whose internal limit can be changed at runtime.

    Already-acquired permits are unaffected — only future acquire() calls
    see the new limit. This is the key property asyncio.Semaphore lacks.
    Active tasks are NEVER interrupted or cancelled when concurrency drops.
    """

    def __init__(self, value: int) -> None:
        self._lock    = threading.Condition(threading.Lock())
        self._value   = value   # current available slots
        self._limit   = value   # configured maximum
        self._waiters = 0

    # ── blocking interface (used from worker threads) ──────────────────

    def acquire_blocking(self, timeout: Optional[float] = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            while self._value <= 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._lock.wait(timeout=remaining)
            self._value -= 1
            return True

    def release(self) -> None:
        with self._lock:
            self._value += 1
            self._lock.notify()

    # ── resize (called only by the manager) ───────────────────────────

    def resize(self, new_limit: int) -> None:
        """
        Increase or decrease the maximum.
        Already-running tasks are NOT interrupted; their slots are reclaimed
        naturally when they call release().
        """
        with self._lock:
            delta        = new_limit - self._limit
            self._limit  = new_limit
            self._value  = max(0, self._value + delta)
            if delta > 0:
                self._lock.notify_all()

    @property
    def limit(self) -> int:
        with self._lock:
            return self._limit

    @property
    def available(self) -> int:
        with self._lock:
            return self._value


# ─────────────────────────────────────────────
# Sliding-window sample store
# ─────────────────────────────────────────────

@dataclass
class _Sample:
    """One recorded API call outcome."""
    success:    bool
    is_429:     bool
    is_timeout: bool
    latency:    float   # seconds


class _SlidingWindow:
    """
    Ring buffer of the last WINDOW_SIZE call outcomes.
    All metric computations use ONLY these samples — no lifetime counters.
    """

    def __init__(self, size: int = WINDOW_SIZE) -> None:
        self._buf: collections.deque = collections.deque(maxlen=size)
        # EMA-tracked baseline latency for this provider (not reset with the window)
        self.baseline_latency: float = 0.5   # seconds, primed to a sane default
        # Lifetime counts (never reset, used for API display only)
        self.total_calls:   int = 0
        self.retry_count:   int = 0
        self.fallback_count: int = 0
        self.total_5xx_count: int = 0

    def add(self, s: _Sample) -> None:
        self._buf.append(s)
        self.total_calls += 1
        # Update baseline via EMA so it tracks long-run typical speed
        self.baseline_latency = (
            EMA_ALPHA * self.baseline_latency
            + (1 - EMA_ALPHA) * s.latency
        )

    def __len__(self) -> int:
        return len(self._buf)

    def __len_unlocked(self) -> int:  # noqa: N802
        """Length without acquiring any external lock — safe only when the
        caller already holds ProviderConcurrencyManager._lock."""
        return len(self._buf)

    # ── derived metrics ────────────────────────────────────────────────

    def _samples(self) -> List[_Sample]:
        return list(self._buf)

    def success_rate(self) -> float:
        samps = self._samples()
        if not samps:
            return 1.0
        return sum(1 for s in samps if s.success) / len(samps)

    def rate_429(self) -> float:
        samps = self._samples()
        if not samps:
            return 0.0
        return sum(1 for s in samps if s.is_429) / len(samps)

    def timeout_rate(self) -> float:
        samps = self._samples()
        if not samps:
            return 0.0
        return sum(1 for s in samps if s.is_timeout) / len(samps)

    def avg_latency(self) -> float:
        samps = self._samples()
        if not samps:
            return self.baseline_latency
        return sum(s.latency for s in samps) / len(samps)

    def latency_ratio(self) -> float:
        """Current avg latency normalised against this provider's own baseline."""
        bl = self.baseline_latency
        if bl <= 0:
            return 1.0
        return self.avg_latency() / bl

    def sample_score(self) -> float:
        """
        Compute a single health sample [0, 1] from the current window.
        Latency is normalised against the provider's own baseline so a
        naturally slow provider is not penalised against a fast one.
        """
        if not self._buf:
            return 1.0

        ratio = self.latency_ratio()
        # ratio 1.0 → score 1.0; ratio 4.0 → score 0.0
        latency_score = max(0.0, 1.0 - (ratio - 1.0) / 3.0)

        score = (
            W_SUCCESS * self.success_rate()
            + W_429    * (1.0 - self.rate_429())
            + W_TIMEOUT * (1.0 - self.timeout_rate())
            + W_LATENCY * latency_score
        )
        return max(0.0, min(1.0, score))


# ─────────────────────────────────────────────
# Per-provider manager
# ─────────────────────────────────────────────

class ProviderConcurrencyManager:
    """
    Tracks health and manages concurrency for a single LLM/search provider.
    One instance per provider — completely independent.
    """

    def __init__(
        self,
        provider:    str,
        max_workers: int = MAX_INSTANCES,
        model:       str = "",
    ) -> None:
        self.provider         = provider
        self._max_workers     = max_workers
        self._current_workers = min(max_workers, MAX_INSTANCES)
        self.sem              = ResizableSemaphore(self._current_workers)
        self._window          = _SlidingWindow(WINDOW_SIZE)
        self._health          = 1.0      # EMA-smoothed composite score
        self._lock            = threading.Lock()
        self._last_adjust     = 0.0      # monotonic timestamp of last resize
        self.model            = model    # informational, updated by callers
        
        # ── Exhaustion tracking ──────────────────────────────────────────
        self._exhausted_until: float = 0.0
        self.times_exhausted:  int = 0
        self.recovery_count:   int = 0
        self._was_exhausted:   bool = False

        # ── Proactive probe state ──────────────────────────────────────────
        self._probe_failed:    bool  = False   # True when last probe returned non-success
        self._probe_error:     str   = ""      # last probe error message (for /provider-health)
        self._probe_status_code: int = 0       # last probe HTTP status code
        self._last_probe_ts:   float = 0.0     # monotonic ts of last probe fire
        self._probe_lock       = threading.Lock()

    # ── public API ────────────────────────────────────────────────────

    def record_outcome(
        self,
        success:    bool,
        is_429:     bool,
        is_timeout: bool,
        latency:    float,
    ) -> None:
        """
        Call once per completed API call.
        Internally updates the sliding-window health score and may resize
        the semaphore if the cooldown period has elapsed.
        """
        with self._lock:
            self._window.add(_Sample(success, is_429, is_timeout, latency))

            if len(self._window) < MIN_SAMPLES_BEFORE_ADJUST:
                return   # not enough data yet — don't change concurrency

            # Update EMA health using latest window sample
            new_sample   = self._window.sample_score()
            self._health = EMA_ALPHA * self._health + (1 - EMA_ALPHA) * new_sample

            self._maybe_adjust()

    def record_retry(self) -> None:
        """Increment the retry counter (does not affect health score)."""
        with self._lock:
            self._window.retry_count += 1

    def record_fallback(self) -> None:
        """Increment the fallback counter (does not affect health score)."""
        with self._lock:
            self._window.fallback_count += 1

    def record_5xx(self) -> None:
        """Increment the 5xx counter (does not affect health score directly here)."""
        with self._lock:
            self._window.total_5xx_count += 1

    def is_exhausted(self) -> bool:
        """Check if provider is currently in a forced cooldown period. Recovers automatically."""
        with self._lock:
            exhausted = time.time() < self._exhausted_until
            if not exhausted and self._was_exhausted:
                self._was_exhausted = False
                self.recovery_count += 1
            return exhausted

    def mark_exhausted(self, wait_seconds: float) -> None:
        """Mark provider as exhausted for a specific duration."""
        with self._lock:
            self._exhausted_until = time.time() + wait_seconds
            self.times_exhausted += 1
            self._was_exhausted = True

    def remaining_cooldown(self) -> float:
        """Return seconds left until recovery."""
        with self._lock:
            return max(0.0, self._exhausted_until - time.time())

    @property
    def health_score(self) -> float:
        with self._lock:
            return round(self._health, 4)

    @property
    def current_workers(self) -> int:
        return self.sem.limit

    def status_label(self) -> str:
        h = self.health_score
        # UNAVAILABLE: probe has fired and failed, AND no successful traffic yet.
        # Distinct from CRITICAL (degraded-under-real-traffic) — here the provider
        # is genuinely unreachable / quota-zeroed before any real request is made.
        if self._probe_failed and self._window._SlidingWindow__len_unlocked() == 0:  # noqa: SLF001
            return "UNAVAILABLE"
        if h >= SCORE_INCREASE_THRESHOLD:
            return "HEALTHY"
        if h >= SCORE_DECREASE_THRESHOLD:
            return "DEGRADED"
        return "CRITICAL"

    def to_dict(self) -> dict:
        """
        Rich snapshot consumed by /provider-health API endpoint.
        All metric values come from the current sliding window.
        Includes probe_status / probe_error from the proactive probe.
        """
        with self._lock:
            w = self._window
            return {
                "provider":           self.provider,
                "health_score":       round(self._health, 4),
                "workers":            self.sem.limit,
                "max_workers":        self._max_workers,
                "success_rate":       round(w.success_rate(), 4),
                "rate_429":           round(w.rate_429(), 4),
                "timeout_rate":       round(w.timeout_rate(), 4),
                "avg_latency":        round(w.avg_latency(), 3),
                "baseline_latency":   round(w.baseline_latency, 3),
                "latency_ratio":      round(w.latency_ratio(), 2),
                "total_calls":        w.total_calls,
                "retry_count":        w.retry_count,
                "fallback_count":     w.fallback_count,
                "5xx_count":          w.total_5xx_count,
                "times_exhausted":    self.times_exhausted,
                "recovery_count":     self.recovery_count,
                "window_size":        len(w),
                "status":             self._status_label_unlocked(),
                "model":              self.model,
                # Proactive probe fields (empty string / 0 when not yet probed)
                "probe_status_code":  self._probe_status_code,
                "probe_error":        self._probe_error,
                "probe_failed":       self._probe_failed,
            }

    # ── private ───────────────────────────────────────────────────────

    def _status_label_unlocked(self) -> str:
        """Must be called while holding self._lock."""
        # UNAVAILABLE: probe fired and failed, no real traffic yet.
        # Must check probe state without acquiring _probe_lock (deadlock risk);
        # _probe_failed is a plain bool read which is safe under the GIL.
        if self._probe_failed and self._window.total_calls == 0:
            return "UNAVAILABLE"
        if self._health >= SCORE_INCREASE_THRESHOLD:
            return "HEALTHY"
        if self._health >= SCORE_DECREASE_THRESHOLD:
            return "DEGRADED"
        return "CRITICAL"

    def _maybe_adjust(self) -> None:
        """Must be called while holding self._lock."""
        now = time.monotonic()
        if now - self._last_adjust < ADJUSTMENT_COOLDOWN_SEC:
            return   # hysteresis — don't thrash

        current = self.sem.limit
        w       = self._window

        if self._health < SCORE_DECREASE_THRESHOLD:
            new = max(WORKERS_MIN, current - STEP_DOWN)
            if new < current:
                self.sem.resize(new)
                self._last_adjust = now
                ratio = w.latency_ratio()
                log.warning(
                    "[AdaptiveConcurrency] REDUCED concurrency  "
                    "| provider=%-10s | %2d → %2d workers "
                    "| health=%.3f | success=%.1f%% | 429=%.1f%% "
                    "| timeout=%.1f%% | latency=%.2f× baseline "
                    "| reason=Provider health degraded (below %.2f threshold)",
                    self.provider,
                    current, new,
                    self._health,
                    w.success_rate()  * 100,
                    w.rate_429()      * 100,
                    w.timeout_rate()  * 100,
                    ratio,
                    SCORE_DECREASE_THRESHOLD,
                )

        elif self._health > SCORE_INCREASE_THRESHOLD:
            new = min(self._max_workers, current + STEP_UP)
            if new > current:
                self.sem.resize(new)
                self._last_adjust = now
                log.info(
                    "[AdaptiveConcurrency] INCREASED concurrency "
                    "| provider=%-10s | %2d → %2d workers "
                    "| health=%.3f | success=%.1f%% | 429=%.1f%% "
                    "| timeout=%.1f%% | latency=%.2f× baseline "
                    "| reason=Provider health sustained above %.2f threshold",
                    self.provider,
                    current, new,
                    self._health,
                    w.success_rate()  * 100,
                    w.rate_429()      * 100,
                    w.timeout_rate()  * 100,
                    w.latency_ratio(),
                    SCORE_INCREASE_THRESHOLD,
                )


# ─────────────────────────────────────────────
# Global registry — one manager per provider key
# ─────────────────────────────────────────────

_MANAGERS: Dict[str, ProviderConcurrencyManager] = {}
_REGISTRY_LOCK = threading.Lock()


def get_provider_manager(
    provider:    str,
    max_workers: int = MAX_INSTANCES,
    model:       str = "",
) -> ProviderConcurrencyManager:
    """
    Return (creating if needed) the singleton ProviderConcurrencyManager for
    the given provider key (e.g. "groq", "gemini", "openai", "tavily").
    """
    with _REGISTRY_LOCK:
        if provider not in _MANAGERS:
            _MANAGERS[provider] = ProviderConcurrencyManager(
                provider, max_workers=max_workers, model=model
            )
        return _MANAGERS[provider]


def record_outcome(
    provider:   str,
    success:    bool,
    is_429:     bool,
    is_timeout: bool,
    latency:    float,
) -> None:
    """Convenience wrapper — records an API outcome for the named provider."""
    get_provider_manager(provider).record_outcome(success, is_429, is_timeout, latency)


def all_health_snapshots() -> list:
    """
    Returns a list of rich to_dict() snapshots for all known providers.
    Consumed by the /provider-health API endpoint.
    """
    with _REGISTRY_LOCK:
        return [m.to_dict() for m in _MANAGERS.values()]


def probe_provider(provider: str) -> dict:
    """
    Fire a lightweight proactive probe for the given provider and record the
    result into the same record_outcome() path reactive traffic uses.

    Results are cached for PROBE_CACHE_TTL_SEC (default 60 s): calling this
    function more frequently than that returns the cached result immediately
    without making another HTTP request.

    Returns a dict:
        { "probed": bool, "cached": bool, "status_code": int,
          "success": bool, "error": str }

    The probe result is also reflected in the manager's to_dict() snapshot
    (probe_status_code, probe_error, probe_failed) and in the status label
    (UNAVAILABLE when probe failed and no real traffic has occurred yet).

    If PROBE_CACHE_TTL_SEC == 0, or no probe definition exists for this
    provider, returns immediately with probed=False.
    """
    if PROBE_CACHE_TTL_SEC <= 0:
        return {"probed": False, "cached": False, "status_code": 0,
                "success": True, "error": "probing disabled"}

    defn = PROVIDER_PROBES.get(provider)
    if not defn:
        return {"probed": False, "cached": False, "status_code": 0,
                "success": True, "error": "no probe defined"}

    mgr = get_provider_manager(provider)

    # ── TTL cache check (under probe lock to prevent thundering herd) ────
    with mgr._probe_lock:
        now = time.monotonic()
        if now - mgr._last_probe_ts < PROBE_CACHE_TTL_SEC:
            return {
                "probed": True, "cached": True,
                "status_code": mgr._probe_status_code,
                "success": not mgr._probe_failed,
                "error": mgr._probe_error,
            }
        mgr._last_probe_ts = now   # reserve the slot before releasing

    # ── Build request ─────────────────────────────────────────────
    try:
        import requests as _req
    except ImportError:
        return {"probed": False, "cached": False, "status_code": 0,
                "success": True, "error": "requests not installed"}

    api_key   = os.getenv(defn["env_key"], "")
    auth_mode = defn.get("auth", "bearer")
    payload   = defn["payload"]
    model_str = defn.get("model", "")
    success_codes = defn.get("success_codes", {200})

    if not api_key:
        err = f"{defn['env_key']} not set in environment"
        with mgr._probe_lock:
            mgr._probe_failed = True
            mgr._probe_error  = err
        return {"probed": True, "cached": False, "status_code": 0,
                "success": False, "error": err}

    if auth_mode == "query":
        url = defn["url_template"].format(model=model_str, key=api_key)
        headers = {"Content-Type": "application/json"}
    else:   # bearer
        url = defn["url"]
        headers = {"Authorization": f"Bearer {api_key}",
                   "Content-Type": "application/json"}

    # ── Fire the probe ───────────────────────────────────────────────
    t0  = time.monotonic()
    status_code = 0
    err_str     = ""
    success     = False
    try:
        resp = _req.post(url, headers=headers, json=payload, timeout=10)
        status_code = resp.status_code
        success     = status_code in success_codes
        if not success:
            try:
                body = resp.json()
                err_str = (body.get("error", {}).get("message")
                           or body.get("error", {}).get("code")
                           or resp.text[:200])
            except Exception:
                err_str = resp.text[:200]
    except Exception as exc:
        err_str = str(exc)

    latency = time.monotonic() - t0
    is_429  = (status_code == 429)

    # ── Feed result into existing record_outcome() path ───────────────
    # This is the single health signal; there is no second parallel system.
    mgr.record_outcome(
        success=success, is_429=is_429, is_timeout=False, latency=latency
    )

    # ── Update probe state cache ────────────────────────────────────
    with mgr._probe_lock:
        mgr._probe_failed      = not success
        mgr._probe_error       = err_str
        mgr._probe_status_code = status_code

    log.info(
        "[ProactiveProbe] provider=%-10s status=%d success=%s "
        "latency=%.2fs error=%s",
        provider, status_code, success, latency, err_str[:80] or "none",
    )
    return {
        "probed": True, "cached": False,
        "status_code": status_code,
        "success": success,
        "error": err_str,
    }


def dynamic_max_workers(provider: str, n_inputs: int) -> int:
    """
    Compute instances = min(n_inputs, current_concurrency_limit).
    Implements the spec: instances = min(number_of_inputs, MAX_INSTANCES).
    Never creates idle workers.
    """
    mgr = get_provider_manager(provider)
    return min(n_inputs, mgr.current_workers)

def generate_provider_summary() -> str:
    """
    Generates a tabular summary of provider metrics at the end of a pipeline run.
    """
    lines = ["\n=====================================", "Provider Summary"]
    with _REGISTRY_LOCK:
        for provider, mgr in _MANAGERS.items():
            lines.append("")
            lines.append(f"{provider.capitalize()}")
            with mgr._lock:
                w = mgr._window
                reqs = w.total_calls
                r_429 = sum(1 for s in w._samples() if s.is_429)
                r_5xx = w.total_5xx_count
                falls = w.fallback_count
                status = mgr._status_label_unlocked()
            lines.append(f"Requests : {reqs}")
            lines.append(f"Successful Requests : {reqs - r_429 - r_5xx}")
            lines.append(f"429 Count : {r_429}")
            lines.append(f"5xx Count : {r_5xx}")
            lines.append(f"Fallback Count : {falls}")
            lines.append(f"Times Marked Exhausted : {mgr.times_exhausted}")
            lines.append(f"Recovery Count : {mgr.recovery_count}")
            lines.append(f"Status : {status}")
    lines.append("=====================================")
    return "\n".join(lines)
