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

    @property
    def health_score(self) -> float:
        with self._lock:
            return round(self._health, 4)

    @property
    def current_workers(self) -> int:
        return self.sem.limit

    def status_label(self) -> str:
        h = self.health_score
        if h >= SCORE_INCREASE_THRESHOLD:
            return "HEALTHY"
        if h >= SCORE_DECREASE_THRESHOLD:
            return "DEGRADED"
        return "CRITICAL"

    def to_dict(self) -> dict:
        """
        Rich snapshot consumed by /provider-health API endpoint.
        All metric values come from the current sliding window.
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
                "window_size":        len(w),
                "status":             self._status_label_unlocked(),
                "model":              self.model,
            }

    # ── private ───────────────────────────────────────────────────────

    def _status_label_unlocked(self) -> str:
        """Must be called while holding self._lock."""
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


def dynamic_max_workers(provider: str, n_inputs: int) -> int:
    """
    Compute instances = min(n_inputs, current_concurrency_limit).
    Implements the spec: instances = min(number_of_inputs, MAX_INSTANCES).
    Never creates idle workers.
    """
    mgr = get_provider_manager(provider)
    return min(n_inputs, mgr.current_workers)
