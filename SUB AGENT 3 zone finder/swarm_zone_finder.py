"""
swarm_zone_finder.py — SUB-AGENT 3: ZONE FINDER ORCHESTRATOR (production v2)
==============================================================================
Production-grade LangGraph orchestrator for Agent 3.

Architecture
------------
  node_load_cities   → node_filter_cities → node_plan_workers
                     → node_run_swarm     → node_finalize → END

Key production features
-----------------------
* Dynamic instance creation
    instances = min(pending_cities, MAX_INSTANCES)
    Never creates idle workers.

* ResizableSemaphore-based concurrency control
    The ThreadPoolExecutor pool size stays fixed for the run's lifetime.
    Concurrency is controlled by the shared ResizableSemaphore from
    adaptive_concurrency.py. When the health score degrades, the semaphore
    limit drops and newly-submitted tasks wait; running tasks are NEVER
    interrupted or cancelled.

* Per-provider health (groq / gemini / openai / tavily)
    One ProviderConcurrencyManager per provider. A 429 on Groq never
    reduces Gemini's concurrency.

* Fault isolation
    Every city executes inside try/except. A city failure marks that city
    as FAILED and stores it in ZoneMetrics.failed_cities; the pipeline
    continues uninterrupted.

* ZoneMetrics instrumentation
    ZONE_METRICS singleton updated on every city start/complete/fail event,
    providing live data for the /agent3/metrics API endpoint.

* Deduplication
    Cities already processed in this session are tracked in _PROCESSED_CITIES
    and skipped instantly (no lock-contention, no LLM calls).

* Stop-signal support
    A threading.Event passed at run time propagates into zone_finders_code
    so retry loops bail out quickly when the user clicks Stop.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Set, TypedDict

# ── path bootstrap (same pattern as the original file) ───────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)

if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)

if _PROJ not in sys.path:
    sys.path.append(_PROJ)

# Remove stale cached supabase_client from another directory
if "supabase_client" in sys.modules:
    _cached_file = getattr(sys.modules["supabase_client"], "__file__", "")
    if _cached_file and os.path.normpath(os.path.dirname(_cached_file)).lower() != \
            os.path.normpath(_HERE).lower():
        del sys.modules["supabase_client"]

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from supabase_client import get_cities
from zone_finders_code import process_city, set_stop_event
from zone_metrics import ZONE_METRICS

# Adaptive concurrency (soft import)
try:
    from adaptive_concurrency import (
        dynamic_max_workers as _dynamic_workers,
        get_provider_manager as _get_mgr,
        MAX_INSTANCES,
        WORKERS_MIN,
    )
    _HAS_ADAPTIVE = True
except ImportError:
    MAX_INSTANCES = int(os.getenv("MAX_INSTANCES", "12"))
    WORKERS_MIN   = int(os.getenv("WORKERS_MIN",   "2"))
    _HAS_ADAPTIVE = False

    def _dynamic_workers(provider: str, n_inputs: int) -> int:
        return min(n_inputs, MAX_INSTANCES)

    class _DummyMgr:
        class sem:
            @staticmethod
            def acquire_blocking(timeout=None): return True
            @staticmethod
            def release(): pass
            limit = MAX_INSTANCES

    def _get_mgr(provider: str):  # type: ignore
        return _DummyMgr()

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Session-scoped deduplication set ─────────────────────────────────
_PROCESSED_CITIES: Set[str] = set()
_PROCESSED_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════════════
#  Agent State
# ═══════════════════════════════════════════════════════════════════

class ZoneAgentState(TypedDict):
    cities:       List[dict]
    pending:      List[dict]   # after freshness filter
    instances:    int          # dynamic worker count
    processed:    int
    failed:       int
    zone_results: List[dict]


# ═══════════════════════════════════════════════════════════════════
#  Node 1 — Load Cities
# ═══════════════════════════════════════════════════════════════════

def node_load_cities(state: ZoneAgentState) -> ZoneAgentState:
    """Fetch all cities from Supabase."""
    cities = get_cities()
    log.info(f"[Agent3] Loaded {len(cities)} cities from Supabase")
    return {
        "cities":       cities,
        "pending":      [],
        "instances":    0,
        "processed":    0,
        "failed":       0,
        "zone_results": [],
    }


# ═══════════════════════════════════════════════════════════════════
#  Node 2 — Filter Cities
# ═══════════════════════════════════════════════════════════════════

def node_filter_cities(state: ZoneAgentState) -> ZoneAgentState:
    """
    Remove cities already processed in this session.
    The Supabase freshness check (ZONE_REFRESH_HOURS) is handled inside
    process_city() via the TTL cache; this node only skips intra-run
    duplicates to avoid submitting the same city twice to the pool.
    """
    pending = []
    skipped = 0
    with _PROCESSED_LOCK:
        for c in state["cities"]:
            key = f"{c.get('city_name','').strip().lower()}::{c.get('country_name', c.get('country', '')).strip().lower()}"
            if key in _PROCESSED_CITIES:
                skipped += 1
            else:
                pending.append(c)

    log.info(
        f"[Agent3] Filter: {len(pending)} cities pending, {skipped} skipped (already processed this session)"
    )
    return {**state, "pending": pending}


# ═══════════════════════════════════════════════════════════════════
#  Node 3 — Plan Workers
# ═══════════════════════════════════════════════════════════════════

def node_plan_workers(state: ZoneAgentState) -> ZoneAgentState:
    """
    Dynamically compute instance count.
    instances = min(pending_cities, MAX_INSTANCES)
    Never creates idle workers.
    """
    n_pending  = len(state["pending"])
    # Use the active health-adjusted concurrency from the adaptive manager
    # (Tavily is typically the binding bottleneck for Agent 3).
    instances  = _dynamic_workers("tavily", n_pending)
    instances  = max(WORKERS_MIN, instances) if n_pending > 0 else 0

    log.info(
        f"[Agent3] Planning: {n_pending} cities → {instances} workers "
        f"(MAX_INSTANCES={MAX_INSTANCES})"
    )
    return {**state, "instances": instances}


# ═══════════════════════════════════════════════════════════════════
#  Worker — one city
# ═══════════════════════════════════════════════════════════════════

def _city_worker(
    city_row:     dict,
    sem,                    # ResizableSemaphore (or None)
    stop_event:   Optional[threading.Event],
    queue_ts:     float,    # monotonic time when the city entered the queue
) -> dict:
    """
    Process one city.
    Acquires the semaphore before starting (respects dynamic concurrency changes).
    Releases the semaphore on completion regardless of outcome.
    Never raises — returns a status dict.
    """
    city_name    = city_row.get("city_name", "").strip()
    country_name = city_row.get("country_name", city_row.get("country", "")).strip()
    dequeue_ts   = time.monotonic()
    queue_wait   = dequeue_ts - queue_ts

    if not city_name or not country_name:
        log.warning(f"[Worker] Skipping row with missing city/country: {city_row}")
        return {"city": city_name, "status": "SKIPPED", "zones": 0, "zones_list": [], "elapsed": 0.0}

    # ── Acquire semaphore (blocks if concurrency limit is reached) ────
    if sem is not None:
        acquired = sem.acquire_blocking(timeout=600)  # 10-min max wait
        if not acquired:
            log.warning(f"[Worker] {city_name}: semaphore acquire timed out — skipping")
            ZONE_METRICS.city_failed(city_name, reason="semaphore_timeout")
            return {"city": city_name, "status": "SKIPPED", "zones": 0, "zones_list": [], "elapsed": 0.0}

    t0 = time.time()
    ZONE_METRICS.city_dequeued(queue_wait_sec=queue_wait)

    try:
        if stop_event is not None and stop_event.is_set():
            log.info(f"[Worker] {city_name}: stop requested before start — skipping")
            ZONE_METRICS.city_failed(city_name, reason="stop_requested")
            return {"city": city_name, "status": "STOPPED", "zones": 0, "zones_list": [], "elapsed": 0.0}

        data        = process_city(city_name, country_name, stop_event=stop_event)
        elapsed     = time.time() - t0
        zones_found = len(data.get("zones", []))
        status      = data.get("status", "SUCCESS")

        if status in ("SUCCESS", "NO_ZONES"):
            ZONE_METRICS.city_completed(city_name, zones_found=zones_found, elapsed=elapsed)
            # Mark as processed so intra-run duplicates are skipped instantly
            with _PROCESSED_LOCK:
                key = f"{city_name.lower()}::{country_name.lower()}"
                _PROCESSED_CITIES.add(key)
            log.info(f"[Worker] {city_name}: {status} — {zones_found} zones in {elapsed:.1f}s")
        else:
            ZONE_METRICS.city_failed(city_name, reason=status)
            log.warning(f"[Worker] {city_name}: returned status={status}")

        return {
            "city":       city_name,
            "status":     status,
            "zones":      zones_found,
            "zones_list": data.get("zones", []),
            "elapsed":    elapsed,
        }

    except Exception as exc:
        elapsed = time.time() - t0
        log.error(f"[Worker] {city_name}: unhandled exception — {exc}")
        ZONE_METRICS.city_failed(city_name, reason=str(exc)[:120])
        return {"city": city_name, "status": "ERROR", "zones": 0, "zones_list": [], "elapsed": elapsed}

    finally:
        if sem is not None:
            sem.release()


# ═══════════════════════════════════════════════════════════════════
#  Node 4 — Run Swarm
# ═══════════════════════════════════════════════════════════════════

def node_run_swarm(state: ZoneAgentState, stop_event: Optional[threading.Event] = None) -> ZoneAgentState:
    """
    Submit all pending cities to a ThreadPoolExecutor.
    Concurrency is bounded by the ResizableSemaphore from the adaptive manager,
    NOT by the ThreadPoolExecutor max_workers (which is set generously so workers
    never queue inside the executor itself — queuing happens at the semaphore).

    This separation means:
    - Already-running tasks are never interrupted when concurrency drops.
    - New tasks wait at the semaphore until a slot is available.
    - The semaphore limit adjusts automatically based on provider health.
    """
    pending   = state["pending"]
    instances = state["instances"]

    if not pending:
        log.info("[Agent3] No pending cities — swarm skipped")
        return {**state, "processed": 0, "failed": 0, "zone_results": []}

    # Reset metrics for this run
    ZONE_METRICS.reset()
    ZONE_METRICS.run_started(len(pending))

    # ── Acquire the adaptive semaphore for the primary provider ──────
    # Tavily is typically the rate-limit bottleneck for Agent 3.
    sem = None
    if _HAS_ADAPTIVE:
        mgr = _get_mgr("tavily")
        # Ensure the semaphore starts at the planned instance count
        if mgr.sem.limit != instances:
            mgr.sem.resize(instances)
        sem = mgr.sem

    log.info(
        f"[Agent3] Swarm starting: {len(pending)} cities, "
        f"{instances} initial workers, semaphore_limit={sem.limit if sem else instances}"
    )

    zone_results: List[dict] = []
    processed    = 0
    failed       = 0

    # ── Pool size = MAX_INSTANCES so the executor never internally queues.
    # The semaphore is the only gate.
    pool_size = MAX_INSTANCES

    with ThreadPoolExecutor(max_workers=pool_size) as executor:
        # Submit all futures immediately; semaphore controls actual concurrency
        queue_timestamps = {}
        futures = {}
        for city_row in pending:
            if stop_event is not None and stop_event.is_set():
                log.info("[Agent3] Stop requested before submitting all cities")
                break
            queue_ts = time.monotonic()
            fut = executor.submit(
                _city_worker,
                city_row,
                sem,
                stop_event,
                queue_ts,
            )
            futures[fut] = city_row
            queue_timestamps[fut] = queue_ts
            ZONE_METRICS.queue_size = len(futures) - len(zone_results)

        # ── Collect results as they complete ─────────────────────────
        for future in as_completed(futures):
            city_row = futures[future]
            ZONE_METRICS.set_worker_snapshot(
                active=sum(1 for f in futures if not f.done()),
                queued=max(0, len(futures) - len(zone_results) - 1),
            )
            try:
                result = future.result()
                zone_results.append(result)

                if result["status"] in ("SUCCESS", "NO_ZONES"):
                    processed += 1
                elif result["status"] == "SKIPPED":
                    pass   # not counted as success or failure
                else:
                    failed += 1

            except Exception as exc:
                city_name = city_row.get("city_name", "?")
                log.error(f"[Agent3] Future raised for {city_name}: {exc}")
                ZONE_METRICS.city_failed(city_name, reason=str(exc)[:120])
                failed += 1

    ZONE_METRICS.set_worker_snapshot(active=0, queued=0)
    log.info(
        f"[Agent3] Swarm complete — processed={processed}, failed={failed}, "
        f"zones_found={ZONE_METRICS.zones_found}, elapsed={ZONE_METRICS.elapsed_sec():.1f}s"
    )
    return {
        **state,
        "processed":    processed,
        "failed":       failed,
        "zone_results": zone_results,
    }


# ═══════════════════════════════════════════════════════════════════
#  Node 5 — Finalize
# ═══════════════════════════════════════════════════════════════════

def node_finalize(state: ZoneAgentState) -> ZoneAgentState:
    """Log run summary and failed cities for downstream retry."""
    metrics = ZONE_METRICS.to_dict()

    log.info("=" * 65)
    log.info("  AGENT 3 — ZONE FINDER SUMMARY")
    log.info("=" * 65)
    log.info(f"  Cities total    : {metrics['cities_total']}")
    log.info(f"  Completed       : {metrics['cities_completed']}")
    log.info(f"  Failed          : {metrics['cities_failed']}")
    log.info(f"  Zones found     : {metrics['zones_found']}")
    log.info(f"  Avg zones/city  : {metrics['avg_zones_per_city']}")
    log.info(f"  Avg proc time   : {metrics['avg_processing_time']}s")
    log.info(f"  Avg queue wait  : {metrics['avg_queue_wait']}s")
    log.info(f"  Retries         : {metrics['retries']}")
    log.info(f"  Fallbacks       : {metrics['fallback_count']}")
    log.info(f"  Provider usage  : {metrics['provider_usage']}")
    log.info(f"  Elapsed         : {metrics['elapsed_sec']}s")

    if metrics["failed_cities"]:
        log.warning(f"  Failed cities   : {[c['city'] for c in metrics['failed_cities']]}")

    log.info("=" * 65)
    return state


# ═══════════════════════════════════════════════════════════════════
#  Build LangGraph
# ═══════════════════════════════════════════════════════════════════

graph = StateGraph(ZoneAgentState)

graph.add_node("load_cities",    node_load_cities)
graph.add_node("filter_cities",  node_filter_cities)
graph.add_node("plan_workers",   node_plan_workers)
graph.add_node("run_swarm",      node_run_swarm)
graph.add_node("finalize",       node_finalize)

graph.set_entry_point("load_cities")

graph.add_edge("load_cities",   "filter_cities")
graph.add_edge("filter_cities", "plan_workers")
graph.add_edge("plan_workers",  "run_swarm")
graph.add_edge("run_swarm",     "finalize")
graph.add_edge("finalize",      END)

agent = graph.compile()


# ═══════════════════════════════════════════════════════════════════
#  Programmatic entry point (called by run_pipeline.py / backend_api)
# ═══════════════════════════════════════════════════════════════════

def run_zone_finder(
    cities: Optional[List[dict]] = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """
    Run the Zone Finder on a given list of city dicts (or load from Supabase
    if cities is None).  Designed for programmatic invocation by the master
    orchestrator or the backend API.

    Returns the final LangGraph state dict with zone_results, processed, failed.
    """
    initial_state: ZoneAgentState = {
        "cities":       cities or [],
        "pending":      [],
        "instances":    0,
        "processed":    0,
        "failed":       0,
        "zone_results": [],
    }

    if cities is not None:
        # If cities were injected, skip node_load_cities
        # (process_city / filter_cities still run)
        initial_state["cities"] = cities
    else:
        initial_state["cities"] = get_cities()

    if stop_event is not None:
        set_stop_event(stop_event)

    # Run the filter → plan → swarm → finalize nodes directly
    state = node_filter_cities(initial_state)
    state = node_plan_workers(state)
    state = node_run_swarm(state, stop_event=stop_event)
    state = node_finalize(state)
    return state


# ═══════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("SUB AGENT 3 — ZONE FINDER (production v2)")
    print("=" * 60)

    initial_state: ZoneAgentState = {
        "cities":       [],
        "pending":      [],
        "instances":    0,
        "processed":    0,
        "failed":       0,
        "zone_results": [],
    }

    result = agent.invoke(initial_state)

    metrics = ZONE_METRICS.to_dict()
    print("\nFinished!")
    print(f"Cities Loaded    : {len(result['cities'])}")
    print(f"Cities Pending   : {len(result['pending'])}")
    print(f"Workers Used     : {result['instances']}")
    print(f"Processed        : {result['processed']}")
    print(f"Failed           : {result['failed']}")
    print(f"Zones Found      : {metrics['zones_found']}")
    print(f"Avg Zones/City   : {metrics['avg_zones_per_city']}")
    print(f"Retries          : {metrics['retries']}")
    print(f"Fallbacks        : {metrics['fallback_count']}")
    print(f"Provider Usage   : {metrics['provider_usage']}")
    if metrics["failed_cities"]:
        print(f"Failed Cities    : {[c['city'] for c in metrics['failed_cities']]}")


if __name__ == "__main__":
    main()