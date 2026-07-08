"""
zone_metrics.py — Thread-safe metrics collector for Agent 3 (Zone Finder)
==========================================================================
Tracks all runtime statistics required by the /agent3/metrics API endpoint
and the execution dashboard.

Usage
-----
  from zone_metrics import ZONE_METRICS

  ZONE_METRICS.city_started("Mumbai")
  ZONE_METRICS.city_completed("Mumbai", zones_found=12, elapsed=38.4)
  ZONE_METRICS.city_failed("Delhi")
  ZONE_METRICS.record_provider("groq")
  ZONE_METRICS.record_retry()
  ZONE_METRICS.record_fallback()

  snapshot = ZONE_METRICS.to_dict()
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ZoneMetrics:
    """
    Centralised, thread-safe metrics store for a single Agent 3 run.
    All numeric fields are updated atomically via an internal threading.Lock.
    """

    # ── city-level counters ───────────────────────────────────────────
    cities_total:     int = 0   # total cities received
    cities_pending:   int = 0   # queued, not yet started
    cities_running:   int = 0   # currently in-flight
    cities_completed: int = 0   # finished successfully
    cities_failed:    int = 0   # raised or returned non-SUCCESS

    # ── zone counts ───────────────────────────────────────────────────
    zones_found:      int = 0   # cumulative zones discovered

    # ── timing accumulators ───────────────────────────────────────────
    _total_processing_sec: float = field(default=0.0, repr=False)
    _total_queue_wait_sec: float = field(default=0.0, repr=False)
    _started_at:           Optional[float] = field(default=None, repr=False)

    # ── retry / fallback ──────────────────────────────────────────────
    retries:        int = 0
    fallback_count: int = 0

    # ── provider usage ────────────────────────────────────────────────
    _provider_usage: Dict[str, int] = field(
        default_factory=lambda: defaultdict(int), repr=False
    )

    # ── worker / queue snapshot ───────────────────────────────────────
    active_workers: int = 0
    queue_size:     int = 0

    # ── failed city list (for post-run retry) ─────────────────────────
    failed_cities: list = field(default_factory=list, repr=False)

    # ── internal ─────────────────────────────────────────────────────
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ── lifecycle ─────────────────────────────────────────────────────

    def run_started(self, total_cities: int) -> None:
        with self._lock:
            self.cities_total   = total_cities
            self.cities_pending = total_cities
            self._started_at    = time.monotonic()

    # ── city events ───────────────────────────────────────────────────

    def city_queued(self) -> None:
        """Call when a city enters the pending queue."""
        with self._lock:
            self.cities_pending = max(0, self.cities_pending)

    def city_dequeued(self, queue_wait_sec: float = 0.0) -> None:
        """Call when a city is popped from the queue and a worker begins."""
        with self._lock:
            self.cities_pending  = max(0, self.cities_pending - 1)
            self.cities_running += 1
            self._total_queue_wait_sec += queue_wait_sec

    def city_started(self, city: str) -> None:
        """Convenience alias — call when city processing begins."""
        with self._lock:
            self.active_workers = max(0, self.active_workers)

    def city_completed(self, city: str, zones_found: int = 0, elapsed: float = 0.0) -> None:
        """Call when a city finishes successfully."""
        with self._lock:
            self.cities_running   = max(0, self.cities_running - 1)
            self.cities_completed += 1
            self.zones_found      += zones_found
            self._total_processing_sec += elapsed

    def city_failed(self, city: str, reason: str = "") -> None:
        """Call when a city fails (exception or non-SUCCESS status)."""
        with self._lock:
            self.cities_running = max(0, self.cities_running - 1)
            self.cities_failed += 1
            self.failed_cities.append({"city": city, "reason": reason})

    # ── event counters ────────────────────────────────────────────────

    def record_retry(self) -> None:
        with self._lock:
            self.retries += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.fallback_count += 1

    def record_provider(self, provider: str) -> None:
        """Increment usage counter for the given provider."""
        with self._lock:
            self._provider_usage[provider] += 1

    def set_worker_snapshot(self, active: int, queued: int) -> None:
        """Update live worker / queue snapshot (called periodically by the swarm)."""
        with self._lock:
            self.active_workers = active
            self.queue_size     = queued

    # ── derived metrics ───────────────────────────────────────────────

    def avg_zones_per_city(self) -> float:
        with self._lock:
            if self.cities_completed == 0:
                return 0.0
            return round(self.zones_found / self.cities_completed, 2)

    def avg_processing_time(self) -> float:
        with self._lock:
            if self.cities_completed == 0:
                return 0.0
            return round(self._total_processing_sec / self.cities_completed, 2)

    def avg_queue_wait(self) -> float:
        cities_started = self.cities_completed + self.cities_failed + self.cities_running
        with self._lock:
            if cities_started == 0:
                return 0.0
            return round(self._total_queue_wait_sec / cities_started, 2)

    def elapsed_sec(self) -> float:
        with self._lock:
            if self._started_at is None:
                return 0.0
            return round(time.monotonic() - self._started_at, 1)

    # ── snapshot ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Return a JSON-serialisable snapshot consumed by /agent3/metrics.
        """
        with self._lock:
            return {
                # city counters
                "cities_total":         self.cities_total,
                "cities_pending":       self.cities_pending,
                "cities_running":       self.cities_running,
                "cities_completed":     self.cities_completed,
                "cities_failed":        self.cities_failed,
                # zone counts
                "zones_found":          self.zones_found,
                "avg_zones_per_city":   self._avg_zones_unlocked(),
                # timing
                "avg_processing_time":  self._avg_proc_unlocked(),
                "avg_queue_wait":       self._avg_wait_unlocked(),
                "elapsed_sec":          self._elapsed_unlocked(),
                # retry / fallback
                "retries":              self.retries,
                "fallback_count":       self.fallback_count,
                # workers / queue
                "active_workers":       self.active_workers,
                "queue_size":           self.queue_size,
                # provider breakdown
                "provider_usage":       dict(self._provider_usage),
                # failed city list for downstream retry
                "failed_cities":        list(self.failed_cities),
            }

    # ── private unlocked helpers (must hold _lock when called) ────────

    def _avg_zones_unlocked(self) -> float:
        if self.cities_completed == 0:
            return 0.0
        return round(self.zones_found / self.cities_completed, 2)

    def _avg_proc_unlocked(self) -> float:
        if self.cities_completed == 0:
            return 0.0
        return round(self._total_processing_sec / self.cities_completed, 2)

    def _avg_wait_unlocked(self) -> float:
        started = self.cities_completed + self.cities_failed + self.cities_running
        if started == 0:
            return 0.0
        return round(self._total_queue_wait_sec / max(1, started), 2)

    def _elapsed_unlocked(self) -> float:
        if self._started_at is None:
            return 0.0
        return round(time.monotonic() - self._started_at, 1)

    def reset(self) -> None:
        """
        Reset all metrics for a new run (called by swarm orchestrator
        at the start of each invocation).
        """
        with self._lock:
            self.cities_total          = 0
            self.cities_pending        = 0
            self.cities_running        = 0
            self.cities_completed      = 0
            self.cities_failed         = 0
            self.zones_found           = 0
            self._total_processing_sec = 0.0
            self._total_queue_wait_sec = 0.0
            self._started_at           = None
            self.retries               = 0
            self.fallback_count        = 0
            self._provider_usage       = defaultdict(int)
            self.active_workers        = 0
            self.queue_size            = 0
            self.failed_cities         = []


# ── singleton (imported by swarm_zone_finder.py and backend_api.py) ──
ZONE_METRICS = ZoneMetrics()
