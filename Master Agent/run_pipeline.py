
import os
import sys
import json
import math
import argparse
import threading
from datetime import datetime

# Locate directories
project_root = os.path.dirname(os.path.abspath(__file__))

# If the script is inside 'Master Agent' or 'master_agent', go up one level to the actual project root
if os.path.basename(project_root).lower().replace(" ", "_") in ("master_agent", "master agent"):
    project_root = os.path.dirname(project_root)

sub1_path = os.path.join(project_root, "SUB AGENT 1")  # FIX: correct path (no sub-subdirectory)
sub2_path = os.path.join(project_root, "SUB AGENT 2")
sub3_path = os.path.join(project_root, "SUB AGENT 3 zone finder")
sub4_path = os.path.join(project_root, "SUB_AGENT 4 sub area mapper")
exec_path = os.path.join(project_root, "execution_engine")

# Append to sys.path dynamically
for p in [sub1_path, sub2_path, sub3_path, sub4_path, exec_path, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

# Force fallback to Groq by removing other keys from environment
os.environ.pop("NVIDIA_API_KEY", None)
os.environ.pop("OPEN_ROUTER_AI_KEY", None)

# Import module functions safely
import city_segmenters_code

# Import Sub-Agent 4's process_zone at module level so import errors are
# caught immediately rather than silently swallowed inside a thread worker.
try:
    from main import process_zone as _process_zone_fn
except Exception as _import_err:
    import warnings
    warnings.warn(
        f"[run_pipeline] Could not import process_zone from main.py: {_import_err}. "
        "Phase 4 (Sub-Area Mapping) will fail. Check that GROQ_API_KEY is set.",
        ImportWarning,
        stacklevel=1,
    )
    _process_zone_fn = None  # type: ignore

# Import orchestrator protocol library
from orchestrator_utils import (
    calculate_batches,
    print_planning_block,
    print_dispatch_block,
    fault_tolerant_dispatch,
    PipelineState,
)

# Adaptive concurrency — soft import so the pipeline still works
# if adaptive_concurrency.py is absent (falls back to a safe default).
try:
    from adaptive_concurrency import dynamic_max_workers as _dynamic_workers
except ImportError:
    def _dynamic_workers(provider: str, n_inputs: int) -> int:
        return min(n_inputs, int(os.getenv("MAX_INSTANCES", "12")))


def parse_args():
    parser = argparse.ArgumentParser(description="Master Agent Orchestrator Pipeline")
    parser.add_argument("--countries", type=str, default=None,
                        help="Comma-separated country list (overrides GDP ranking)")
    parser.add_argument("--top-n", type=int, default=None,
                        help="Use top N countries from GDP_data.json (Agent 1 output)")
    parser.add_argument("--refresh-gdp", action="store_true",
                        help="Re-run Agent 1 (GDP Ranker) to refresh GDP_data.json")
    parser.add_argument("--cities", type=str, default=None,
                        help="Comma-separated cities list to directly start from (skips GDP and city segmentation)")
    parser.add_argument("--zones", type=str, default=None,
                        help="Comma-separated zones to directly start from (skips steps 1-3)")
    parser.add_argument("--max-scrolls", type=int, default=8,
                        help="Max scrolls for Playwright scraper (default: 8)")
    parser.add_argument("--max-scrapers", type=int, default=3,
                        help="Max concurrent browser instances for scraping (default: 3)")
    parser.add_argument("--skip-supabase", action="store_true",
                        help="Skip inserting subareas/results into Supabase")
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1 — Global GDP Ranking (Agent 1) — Sequential
# ═══════════════════════════════════════════════════════════════════

def phase_1_gdp_ranking(state, args):
    """
    Spawn exactly 1 instance of Agent 1 (GDP Ranker).
    Uses pre-computed GDP_data.json by default. Use --refresh-gdp to re-run.
    """
    # If user passed explicit countries, skip Agent 1 entirely
    if args.countries:
        countries = [c.strip() for c in args.countries.split(",") if c.strip()]
        print_planning_block(
            phase_num=1, phase_name="GDP Ranking",
            total_items=len(countries), c_max=len(countries), K=1,
            item_label="countries"
        )
        print_dispatch_block(
            agent_name="Agent 1 — GDP Ranker",
            instance_id="Agent1-Clone-01",
            input_data=countries,
            expected_output_desc="User-supplied country list (GDP ranking skipped)"
        )
        print(f"  [OK] Agent1-Clone-01 completed (user-supplied {len(countries)} countries).")
        state.gdp_ranked_countries = [
            {"country_name": c, "gdp_rank": i + 1} for i, c in enumerate(countries)
        ]
        return

    # Load GDP data from Agent 1's pre-computed output
    gdp_path = os.path.join(project_root, "GDP_data.json")

    if args.refresh_gdp or not os.path.exists(gdp_path):
        print("[Agent 1] --refresh-gdp flag set or GDP_data.json missing.")
        print("[Agent 1] To generate GDP_data.json, run:")
        print(f"  python \"{os.path.join(sub1_path, 'GDP ranker.py')}\"")
        print("[Agent 1] Using fallback: India only.")
        state.gdp_ranked_countries = [
            {"country_name": "India", "gdp_rank": 1}
        ]
        return

    print_planning_block(
        phase_num=1, phase_name="GDP Ranking",
        total_items=1, c_max=1, K=1,
        item_label="global request"
    )
    print_dispatch_block(
        agent_name="Agent 1 — GDP Ranker",
        instance_id="Agent1-Clone-01",
        input_data=["Load GDP_data.json"],
        expected_output_desc="Ordered list of N countries by GDP"
    )

    with open(gdp_path, "r", encoding="utf-8") as f:
        gdp_data = json.load(f)

    all_countries = gdp_data.get("data", [])

    # Apply top-N filter if specified
    if args.top_n:
        all_countries = all_countries[:args.top_n]
        print(f"  [Agent1] Filtered to top {args.top_n} countries by GDP.")

    state.gdp_ranked_countries = all_countries
    print(f"  [OK] Agent1-Clone-01 completed. Loaded {len(all_countries)} countries from GDP_data.json.")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 2 — City Segmentation (Agent 2) — Massive Parallel
# ═══════════════════════════════════════════════════════════════════

def phase_2_city_segmentation(state, provider: str = "groq", stop_event=None):
    """
    Take N countries from Phase 1.
    CALCULATE: K2 = ceil(N / C_max) with C_max = 1 country per instance.
    DISPATCH: K2 identical Agent 2 instances in parallel (1-to-1 thread
    isolation). C_MAX was changed from 3 -> 1 because process_country() makes
    exactly one LLM call per country; grouping 3 per thread never batched
    anything, it only serialised 3 sequential calls inside one thread at the
    cost of load-balancing and per-country retry granularity.

    provider: which LLM to use for city classification calls
    ("groq" | "gemini" | "openai"). Manual choice, forwarded to
    city_segmenters_code.process_country(). Defaults to "groq", matching
    behavior before provider choice existed.
    """
    print(f"[TRACE-01] Entering Agent 2")
    countries = [c.get("country_name", c) if isinstance(c, dict) else c
                 for c in state.gdp_ranked_countries]

    if not countries:
        print("[TRACE-02] No countries to process. Skipping.")
        return

    print(f"[TRACE-03] Countries received: {len(countries)}")
    N = len(countries)
    C_MAX = 1  # 1-to-1 thread isolation (0 extra LLM cost, perfectly load-balanced)

    batches = calculate_batches(countries, c_max=C_MAX, agent_name="Agent2")
    K = len(batches)
    print(f"[TRACE-04] Number of batches: {K}")
    
    if state.orchestrator is not None and state.orchestrator.metrics:
        _am = state.orchestrator.metrics.agents.get("2")
        if _am is not None:
            _am.input_count = K
            print(f"[TRACE-05] Updating input_count to {K}")

    print_planning_block(
        phase_num=2, phase_name="City Segmentation",
        total_items=N, c_max=C_MAX, K=K,
        item_label="countries"
    )

    # Print dispatch blocks
    for batch in batches:
        print_dispatch_block(
            agent_name="Agent 2 — City Segmentor",
            instance_id=batch["instance_id"],
            input_data=batch["items"],
            expected_output_desc='{ "country": { "tier_1": [...], "tier_2": [...], "tier_3": [...] } }'
        )

    _registry_lock = threading.Lock()
    # Seed seen-set from any cities already in state (checkpoint resume safety).
    # Key is (city_name, country) — NOT bare city_name — so the same city name
    # appearing under two different countries (e.g. "Springfield, US" vs
    # "Springfield, AU") is kept as two distinct entries. Name-only dedup was
    # the original behaviour and silently discarded legitimate cities.
    global_seen_cities = {(c.get("city"), c.get("country")) for c in state.all_cities if c.get("city")}

    # Worker function for fault-tolerant dispatch
    def segmentation_worker(country_batch, instance_id):
        import time
        import traceback
        import requests
        
        # Soft import for adaptive concurrency health tracking
        try:
            from adaptive_concurrency import record_outcome as _record_outcome
        except ImportError as e:
            def _record_outcome(*a, **kw): pass
            print(f"  [{instance_id}] WARNING: record_outcome unavailable — health scoring disabled for Agent 2 ({e})")

        print(f"  [{instance_id}] Processing {len(country_batch)} countries: {country_batch}")
        results = {}
        for idx, country_name in enumerate(country_batch):
            if stop_event is not None and stop_event.is_set():
                print(f"  [{instance_id}] Stop requested — halting before next country.")
                break
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                start_ts = time.monotonic()
                try:
                    data = city_segmenters_code.process_country(country_name, provider=provider)
                    latency = time.monotonic() - start_ts
                    _record_outcome(provider, True, False, False, latency)
                    
                    results[country_name] = data
                    
                    # Real-time state merge for "No data yet" bug & dashboard live count
                    new_city_names = []
                    with _registry_lock:
                        print(f"  [{instance_id}] Merging {country_name} into state ({len(state.all_cities)} cities so far)...")
                        state.master_city_registry[country_name] = data
                        for tier_idx, tier_key in enumerate(["tier_1_cities", "tier_2_cities", "tier_3_cities"]):
                            for item in data.get(tier_key, []):
                                city_name = item.get("city_name")
                                if city_name:
                                    # (city_name, country) pair-based dedup — intentional design:
                                    # allows the same city name once per country so distinct cities
                                    # that share a name across countries are not silently discarded.
                                    # Do NOT simplify to name-only dedup.
                                    pair = (city_name, country_name)
                                    if pair not in global_seen_cities:
                                        global_seen_cities.add(pair)
                                        new_city_names.append(city_name)
                                        state.all_cities.append({
                                            "city": city_name, "country": country_name, "tier": tier_idx + 1
                                        })
                        
                        if state.orchestrator is not None and state.orchestrator.metrics:
                            _am = state.orchestrator.metrics.agents.get("2")
                            if _am is not None:
                                _am.record_output(new_city_names)
                            else:
                                print("[run_pipeline] WARNING: metrics key '2' not found — skipping record_output for Agent 2")
                                
                    break
                except ValueError as ve:
                    # Validation/Parsing error (LLM returned bad shape) - Retryable
                    _record_outcome(provider, False, False, False, time.monotonic() - start_ts)
                    if attempt < max_retries:
                        wait_secs = 10 * attempt
                        print(f"  [{instance_id}] Validation Error for {country_name} (attempt {attempt}): {ve} — retrying in {wait_secs}s...")
                        time.sleep(wait_secs)
                    else:
                        print(f"  [{instance_id}] ERROR for {country_name}: {ve}")
                        results[country_name] = {"status": "FAILED", "error": str(ve)}
                        break
                except Exception as e:
                    err_str = str(e).lower()
                    is_rate_limit = any(kw in err_str for kw in ["429", "rate limit", "rate_limit", "too many requests"])
                    
                    # Type-aware transient check
                    is_network_err = isinstance(e, (requests.exceptions.RequestException, TimeoutError, ConnectionError))
                    is_transient = is_rate_limit or is_network_err or any(kw in err_str for kw in ["timeout", "connection", "read error"])
                    
                    if is_transient:
                        _record_outcome(provider, False, is_rate_limit, "timeout" in err_str or isinstance(e, TimeoutError), time.monotonic() - start_ts)
                        if is_rate_limit:
                            city_segmenters_code._report_rate_limit(provider, f"country={country_name}, attempt={attempt}")
                        if attempt < max_retries:
                            wait_secs = 20 * attempt  # 20s, 40s backoff
                            print(f"  [{instance_id}] Transient/Rate limit for {country_name} (attempt {attempt}) — waiting {wait_secs}s before retry...")
                            time.sleep(wait_secs)
                        else:
                            tb = traceback.format_exc()
                            print(f"  [{instance_id}] ERROR for {country_name}: {e}")
                            results[country_name] = {"status": "FAILED", "error": str(e), "traceback": tb}
                            break
                    else:
                        # Genuine code bug / non-transient exception -> Fail fast, NO retry
                        tb = traceback.format_exc()
                        print(f"  [{instance_id}] UNEXPECTED_ERROR: {type(e).__name__} for {country_name} — {e}")
                        results[country_name] = {"status": "FAILED", "error": f"UNEXPECTED_ERROR: {e}", "traceback": tb}
                        break
        return results

    # Execute with fault tolerance
    # Agent 2's concurrency is driven by the adaptive manager:
    effective_workers = _dynamic_workers(provider, K)
    
    def _on_active_change(delta: int):
        if state.orchestrator is not None and state.orchestrator.metrics:
            _am = state.orchestrator.metrics.agents.get("2")
            if _am is not None:
                _am.change_active_instances(delta)
            else:
                print("[run_pipeline] WARNING: metrics key '2' not found — skipping change_active_instances for Agent 2")

    all_results, failures = fault_tolerant_dispatch(
        worker_fn=segmentation_worker,
        batches=batches,
        agent_name="Agent 2 — City Segmentor",
        max_workers=effective_workers,
        on_active_change=_on_active_change,
    )

    for f in failures:
        state.log_failure("Phase 2 — City Segmentation", f)



    print(f"\n  [Phase 2] Master City Registry built. {len(state.all_cities)} cities across "
          f"{len(state.master_city_registry)} countries.")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 3 — Zone Finding (Agent 3) — Massive Parallel
# ═══════════════════════════════════════════════════════════════════

def phase_3_zone_finding(state, stop_event=None):
    """
    Flatten Master City Registry into M cities.
    CALCULATE: K3 = ceil(M / C_max) with C_max = 1 city per instance.
    DISPATCH: K3 identical Agent 3 instances in parallel (1-to-1 thread
    isolation). C_MAX was changed from 4 -> 1 because process_city() makes
    exactly one LLM+Tavily call per city; grouping 4 per thread never batched
    anything, it only serialised 4 sequential calls inside one thread at the
    cost of load-balancing and per-city retry granularity.

    stop_event: optional threading.Event. When set, in-progress city loops
    bail out after the current city finishes rather than waiting for the
    whole batch/phase to complete naturally. Checked between cities (not
    mid-API-call) since interrupting an in-flight HTTP request isn't safe.
    """
    if not state.all_cities:
        print("  [Phase 3] No cities to process. Skipping.")
        return

    from zone_finders_code import _EXHAUSTED_PROVIDERS
    _EXHAUSTED_PROVIDERS.clear()  # fresh fallback chain for this run (module state is shared across sessions)

    M = len(state.all_cities)
    C_MAX = 1  # 1-to-1 thread isolation

    batches = calculate_batches(state.all_cities, c_max=C_MAX, agent_name="Agent3")
    K = len(batches)
    
    if state.orchestrator is not None and state.orchestrator.metrics:
        _am = state.orchestrator.metrics.agents.get("3")
        if _am is not None:
            _am.input_count = K

    print_planning_block(
        phase_num=3, phase_name="Zone Finding",
        total_items=M, c_max=C_MAX, K=K,
        item_label="cities"
    )

    # Print dispatch blocks
    for batch in batches:
        city_names = [c["city"] for c in batch["items"]]
        print_dispatch_block(
            agent_name="Agent 3 — Zone Finder",
            instance_id=batch["instance_id"],
            input_data=city_names,
            expected_output_desc='{ "city": { "zones": [...] } }'
        )

    _registry_lock = threading.Lock()

    # Worker function — processes a batch of city dicts
    def zone_finder_worker(city_batch, instance_id):
        import time
        import traceback
        import requests
        from zone_finders_code import process_city
        print(f"  [{instance_id}] Processing {len(city_batch)} cities...")
        results = []
        for city_info in city_batch:
            if stop_event is not None and stop_event.is_set():
                print(f"  [{instance_id}] Stop requested — halting before next city.")
                break
            city_name = city_info["city"]
            country = city_info["country"]
            
            # Thundering-herd protection: stagger each city by 1 s before its
            # first API call. The adaptive concurrency governor throttles maximum
            # concurrent workers in steady state, but cannot react to an initial
            # burst because it has no latency/outcome data yet — all workers
            # start in the same millisecond and the first wave of requests hits
            # Tavily before the health scorer has any signal to step down on.
            # This sleep specifically guards that initial-burst window.
            # Do NOT remove without replacing with an equivalent stagger mechanism.
            time.sleep(1)
            
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    data = process_city(city_name, country, stop_event=stop_event)
                    if data and data.get("status") in ("SUCCESS", "NO_ZONES", "STOPPED"):
                        results.append(data)
                        
                        # Real-time lock-protected merge (handles 0 zones correctly)
                        zones = [z["zone_name"] for z in data.get("zones", []) if z.get("zone_name")]
                        with _registry_lock:
                            if city_name:
                                state.master_zone_registry[(city_name, country)] = zones
                            if state.orchestrator is not None and state.orchestrator.metrics:
                                _am = state.orchestrator.metrics.agents.get("3")
                                if _am is not None:
                                    _am.record_output(zones)
                                else:
                                    print("[run_pipeline] WARNING: metrics key '3' not found — skipping record_output for Agent 3")
                        
                        break
                    else:
                        # process_city returned None or an unrecognised status
                        # (not SUCCESS / NO_ZONES / STOPPED). Real exceptions from
                        # discover_zones now re-raise and are caught above, so this
                        # path covers only unexpected None returns or unknown statuses.
                        raise ValueError(f"Zone finding failed: {data.get('error', 'unknown') if data else 'None returned'}")
                        
                except Exception as e:
                    err_str = str(e).lower()
                    is_transient = (
                        isinstance(e, (requests.exceptions.RequestException, TimeoutError, ConnectionError, ValueError)) 
                        or any(kw in err_str for kw in ["429", "timeout", "connection", "read error", "rate limit"])
                    )
                    if is_transient:
                        if attempt < max_retries:
                            wait_secs = 20 * attempt
                            print(f"  [{instance_id}] Transient error for {city_name} (attempt {attempt}) — waiting {wait_secs}s before retry...")
                            time.sleep(wait_secs)
                        else:
                            tb = traceback.format_exc()
                            print(f"  [{instance_id}] ERROR for {city_name}: {e}")
                            state.log_failure("Agent 3 — Zone Discovery", {"instance_id": f"Agent3-{city_name}", "error": str(e), "traceback": tb})
                            break
                    else:
                        # Genuine code bug -> Fail fast
                        tb = traceback.format_exc()
                        print(f"  [{instance_id}] UNEXPECTED_ERROR: {type(e).__name__} for {city_name} — {e}")
                        state.log_failure("Agent 3 — Zone Discovery", {"instance_id": f"Agent3-{city_name}", "error": str(e), "traceback": tb})
                        break
                        
        return results

    # Execute with fault tolerance.
    # Agent 3's concurrency is driven by the adaptive manager against the
    # "tavily" provider key (Tavily is the bottleneck here, not the LLM).
    # Starts at MAX_INSTANCES (default 12), steps down automatically when
    # Tavily 429/432 errors cause the health score to drop below 0.70.
    effective_workers = _dynamic_workers("tavily", K)
    
    def _on_active_change(delta: int):
        if state.orchestrator is not None and state.orchestrator.metrics:
            _am = state.orchestrator.metrics.agents.get("3")
            if _am is not None:
                _am.change_active_instances(delta)
            else:
                print("[run_pipeline] WARNING: metrics key '3' not found — skipping change_active_instances for Agent 3")
            
    all_results, failures = fault_tolerant_dispatch(
        worker_fn=zone_finder_worker,
        batches=batches,
        agent_name="Agent 3 — Zone Finder",
        max_workers=effective_workers,
        on_active_change=_on_active_change,
    )

    # Log failures
    for f in failures:
        state.log_failure("Phase 3 — Zone Finding", f)

    print(f"\n  [Phase 3] Master Zone Registry built.")
    total_zones = sum(len(z) for z in state.master_zone_registry.values())
    print(f"  Total zones discovered: {total_zones}")
    for (city, country), zones in state.master_zone_registry.items():
        print(f"    • {city}, {country}: {len(zones)} zones — {zones}")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 4 — Sub-Area Mapper (Agent 5) — Hyper-Parallel
# ═══════════════════════════════════════════════════════════════════

def phase_4_subarea_mapper(state, provider: str = "groq", stop_event=None):
    """
    Flatten Master Zone Registry into Z zones.
    CALCULATE: K5 = ceil(Z / C_max) with C_max = 2 zones per instance.
    DISPATCH: K5 identical Agent 5 instances in parallel.
    C_MAX=2 is retained here (unlike Agents 2/3 which moved to 1) because
    process_zone() takes one zone per call — grouping 2 per thread gives
    modest dispatch-overhead reduction at leaf level with no extra LLM cost.
    Confirmed: process_zone(zone_name, city, country) signature is 1-zone-per-call.

    provider: which LLM to use for zone-to-subarea mapping calls
    ("groq" | "gemini" | "openai"). Manual choice, passed through to
    process_zone() in SUB_AGENT 4/main.py. Defaults to "groq", matching
    behavior before provider choice existed.
    """
    # Globally flatten all zones into one list
    all_zone_items = []
    for (city, country), zones in state.master_zone_registry.items():
        for zone_name in zones:
            all_zone_items.append({
                "zone_name": zone_name,
                "city": city,
                "country": country,
            })

    if not all_zone_items:
        print("  [Phase 4] No zones to process. Skipping.")
        return

    Z = len(all_zone_items)
    C_MAX = 2  # 1-3 zones per instance (hyper-parallel) per spec

    batches = calculate_batches(all_zone_items, c_max=C_MAX, agent_name="Agent5")
    K = len(batches)
    
    if state.orchestrator is not None and state.orchestrator.metrics:
        _am = state.orchestrator.metrics.agents.get("4")
        if _am is not None:
            _am.input_count = K

    print_planning_block(
        phase_num=4, phase_name="Sub-Area Mapping (Agent 5)",
        total_items=Z, c_max=C_MAX, K=K,
        item_label="zones"
    )

    # Print dispatch blocks
    for batch in batches:
        zone_names = [z["zone_name"] for z in batch["items"]]
        print_dispatch_block(
            agent_name="Agent 5 — Sub-Area Mapper",
            instance_id=batch["instance_id"],
            input_data=zone_names,
            expected_output_desc='{ "zone": { "subareas": [...] } }'
        )

    # Worker function — processes a batch of zone dicts
    def subarea_worker(zone_batch, instance_id):
        # Use the module-level import; fall back to a fresh import if it
        # wasn't available at startup (e.g., keys loaded after startup).
        import traceback
        process_zone = _process_zone_fn
        if process_zone is None:
            try:
                from main import process_zone as process_zone  # noqa: F811
            except Exception as e:
                print(f"  [{instance_id}] CRITICAL: Cannot import process_zone: {e}")
                return []
        print(f"  [{instance_id}] Processing {len(zone_batch)} zones...")
        results = []
        for zone_info in zone_batch:
            if stop_event is not None and stop_event.is_set():
                print(f"  [{instance_id}] Stop requested — halting before next zone.")
                break
            zone_name = zone_info["zone_name"]
            city = zone_info["city"]
            country = zone_info["country"]
            try:
                result_data = process_zone(zone_name, city, country, provider=provider)
                
                # Handle dict return type from updated process_zone
                output_path = result_data.get("path") if isinstance(result_data, dict) else result_data
                status = result_data.get("status", "SUCCESS") if isinstance(result_data, dict) else "SUCCESS"
                
                if status == "SUCCESS":
                    results.append({
                        "zone_name": zone_name,
                        "city": city,
                        "country": country,
                        "output_path": output_path,
                        "status": status,
                        "_raw_data": result_data if isinstance(result_data, dict) else None,
                    })
                else:
                    err_msg = result_data.get("error", "Unknown error") if isinstance(result_data, dict) else "Non-success status"
                    print(f"  [{instance_id}] Zone mapping returned non-SUCCESS for {zone_name}")
                    state.log_failure("Agent 4 — Sub-Area Mapping", {
                        "instance_id": f"Agent4-{zone_name}",
                        "error": f"Sub-area mapping failed for zone {zone_name}: {err_msg}",
                        "traceback": ""
                    })
            except Exception as e:
                tb = traceback.format_exc()
                print(f"  [{instance_id}] ERROR for zone {zone_name}: {e}")
                state.log_failure("Agent 4 — Sub-Area Mapping", {
                    "instance_id": f"Agent4-{zone_name}",
                    "error": f"Sub-area mapping failed for zone {zone_name}: {e}",
                    "traceback": tb
                })
        return results

    def _on_active_change(delta: int):
        # The guard allows agents to run standalone without an orchestrator wrapper.
        # Fails silently instead of crashing when 'run_pipeline.py' is executed directly.
        if state.orchestrator is not None and state.orchestrator.metrics:
            _am = state.orchestrator.metrics.agents.get("4")
            if _am is not None:
                _am.change_active_instances(delta)
            else:
                print("[run_pipeline] WARNING: metrics key '4' not found — skipping change_active_instances for Agent 4")

    # Execute with fault tolerance
    # Wired to the adaptive governor so large zone counts don't spin up
    # an unbounded thread pool (max_workers=K with no ceiling is a real
    # risk when Z is large — extras queue safely inside ThreadPoolExecutor).
    effective_workers = _dynamic_workers(provider, K)
    all_results, failures = fault_tolerant_dispatch(
        worker_fn=subarea_worker,
        batches=batches,
        agent_name="Agent 4 — Sub-Area Mapper",
        max_workers=effective_workers,
        on_active_change=_on_active_change,
    )

    # Log failures
    for f in failures:
        state.log_failure("Phase 4 — Sub-Area Mapping", f)

    # # Parse output files and merge into Master Subarea Registry
    # for result in all_results:
    #     if not isinstance(result, dict):
    #         continue
    # Parse output files and merge into Master Subarea Registry
    for batch_result in all_results:
        # Worker returns a LIST of zone result dicts — handle both shapes
        items = batch_result if isinstance(batch_result, list) else [batch_result]
        for result in items:
            if not isinstance(result, dict):
                continue
            res_path = result.get("output_path")
            zone_name = result.get("zone_name", "")
            city = result.get("city", "")
            country = result.get("country", "")

            if not res_path or not os.path.exists(res_path):
                # --- Fallback: try to get subareas directly from the result dict ---
                raw_data = result.get("_raw_data")
                if isinstance(raw_data, dict) and "results" in raw_data:
                    # process_zone returned data inline (no file I/O needed)
                    parsed_zone = raw_data.get("input", {}).get("zone_name", zone_name)
                    subareas = raw_data.get("results", [])
                    state.master_subarea_registry[(parsed_zone, city, country)] = subareas
                    for item in subareas:
                        state.all_subarea_rows.append({
                            "zone_name": parsed_zone,
                            "subarea_name": item.get("subarea_name", ""),
                            "parent_zone": item.get("parent_zone", ""),
                            "business_volume": item.get("business_volume", 300),
                            "city": item.get("city", city),
                            "country": country,
                            "source_url": item.get("source_url", ""),
                            "retrieved_at": item.get("retrieved_at", datetime.now().isoformat()),
                            "status": item.get("status", "SUCCESS"),
                        })
                else:
                    print(f"  [Phase 4] No output file and no inline data for zone '{zone_name}' — skipping.")
                continue
            try:
                with open(res_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Parse JSON
                start = content.find("{")
                end = content.rfind("}") + 1
                data = json.loads(content[start:end])

                parsed_zone = data.get("input", {}).get("zone_name", zone_name)
                subareas = data.get("results", [])
                state.master_subarea_registry[(parsed_zone, city, country)] = subareas

                for item in subareas:
                    state.all_subarea_rows.append({
                        "zone_name": parsed_zone,
                        "subarea_name": item.get("subarea_name", ""),
                        "parent_zone": item.get("parent_zone", ""),
                        "business_volume": item.get("business_volume", 300),
                        "city": item.get("city", city),
                        "country": country,
                        "source_url": item.get("source_url", ""),
                        "retrieved_at": item.get("retrieved_at", datetime.now().isoformat()),
                        "status": item.get("status", "SUCCESS"),
                    })
            except Exception as e:
                print(f"  [ERROR] Failed parsing subarea output file {res_path}: {e}")
    # FIX: Removed orphaned duplicate code block that ran after the inner loop
    # using the stale `result` variable from the last iteration, causing double-inserts.

    print(f"\n  [Phase 4] Sub-Area Mapping completed. Found {len(state.all_subarea_rows)} total sub-areas.")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 4.5 — Supabase Insert (Optional)
# ═══════════════════════════════════════════════════════════════════

def phase_4_5_supabase_insert(state, skip_supabase):
    """Insert subarea metadata into Supabase if configured."""
    if not state.all_subarea_rows or skip_supabase:
        return

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("  [Info] SUPABASE_URL or SUPABASE_KEY not found in env. Skipping Supabase insert.")
        return

    try:
        from supabase import create_client
        print(f"\n-> Phase 4.5: Inserting {len(state.all_subarea_rows)} subarea rows into Supabase...")
        supabase = create_client(supabase_url, supabase_key)
        response = supabase.table("subareas").insert(state.all_subarea_rows).execute()
        print(f"   [OK] Successfully inserted {len(state.all_subarea_rows)} subareas into 'subareas' table.")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        state.log_failure("Agent 4 — Sub-Area Mapping", {
            "instance_id": "Supabase-Subareas-Insert",
            "error": f"Supabase insert failed: {e}",
            "traceback": tb
        })
        print(f"   [Warning] Supabase insert failed (might be duplicates handled by Agent 5): {e}")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 5.5 — Supabase Leads Insert (Optional)
# ═══════════════════════════════════════════════════════════════════

def phase_5_5_supabase_insert_leads(state, skip_supabase):
    """Insert scraped companies/leads into execution_results table if configured."""
    if not state.scraped_companies or skip_supabase:
        return

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("  [Info] SUPABASE_URL or SUPABASE_KEY not found in env. Skipping Supabase leads insert.")
        return

    try:
        from supabase import create_client
        print(f"\n-> Phase 5.5: Inserting {len(state.scraped_companies)} lead rows into Supabase...")
        supabase = create_client(supabase_url, supabase_key)
        
        # Prepare the rows for execution_results schema
        rows = []
        for comp in state.scraped_companies:
            rows.append({
                "subarea_name": comp.get("subarea_name", ""),
                "zone_name": comp.get("zone_name", ""),
                "city_name": comp.get("city_name", ""),
                "country_name": comp.get("country_name", ""),
                "company_name": comp.get("company_name", ""),
                "category": comp.get("category", ""),
                "priority": comp.get("priority", 1),
                "created_at": comp.get("created_at", datetime.now().isoformat())
            })
            
        response = supabase.table("execution_results").insert(rows).execute()
        print(f"   [OK] Successfully inserted {len(rows)} leads into 'execution_results' table.")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        state.log_failure("Execution Engine — Company Discovery", {
            "instance_id": "Supabase-Leads-Insert",
            "error": f"Supabase leads insert failed: {e}",
            "traceback": tb
        })
        print(f"   [Warning] Supabase leads insert failed: {e}")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 5 — Playwright Scraper (Agent 6) — Hyper-Parallel
# ═══════════════════════════════════════════════════════════════════

def phase_5_lead_scraper(state, max_scrolls, max_scrapers, stop_event=None):
    """
    Construct scraper payload from sub-areas.
    CALCULATE: K6 = ceil(S / C_max) with C_max = 2 subareas per instance.
    DISPATCH: K6 identical Agent 6 instances in parallel.
    """
    print(f"\n-> Phase 5: Constructing Lead Scraper Payloads for all sub-areas...")

    all_subareas = []
    for (zone_name, city, country), subareas in state.master_subarea_registry.items():
        for sa in subareas:
            subarea_name = sa.get("subarea_name", "")
            volume = sa.get("business_volume", 300)

            if subarea_name:
                all_subareas.append({
                    "subarea_name": subarea_name,
                    "zone_name": zone_name,
                    "city": city,
                    "country": country,
                })
                print(f"   [Queueing] '{subarea_name}' in {city} (vol: {volume})")

    if not all_subareas:
        print("  [Phase 5] No subareas to process. Skipping.")
        return

    S = len(all_subareas)
    C_MAX = 2  # 1-3 subareas per instance (hyper-parallel)

    batches = calculate_batches(all_subareas, c_max=C_MAX, agent_name="Agent6")
    K = len(batches)
    
    if state.orchestrator is not None and state.orchestrator.metrics:
        _am = state.orchestrator.metrics.agents.get("5")
        if _am is not None:
            _am.input_count = K

    print_planning_block(
        phase_num=5, phase_name="Lead Scraping (Agent 6)",
        total_items=S, c_max=C_MAX, K=K,
        item_label="subareas"
    )

    # Print dispatch blocks
    for batch in batches:
        subarea_names = [s["subarea_name"] for s in batch["items"]]
        print_dispatch_block(
            agent_name="Agent 6 — Playwright Scraper",
            instance_id=batch["instance_id"],
            input_data=subarea_names,
            expected_output_desc='[{ "company_name": "...", "category": "...", "priority": N }]'
        )

    # Worker function — processes a batch of subareas
    def scraper_worker(subarea_batch, instance_id):
        from execution_worker import scrape_subarea
        import config as exec_config
        import traceback
        
        # Dynamically apply CLI scroll overrides
        exec_config.SCROLL_ITERATIONS = max_scrolls
        
        print(f"  [{instance_id}] Scraping {len(subarea_batch)} subareas...")
        all_companies = []
        for sa_info in subarea_batch:
            if stop_event is not None and stop_event.is_set():
                print(f"  [{instance_id}] Stop requested — halting before next subarea.")
                break
            try:
                results = scrape_subarea(
                    sa_info["subarea_name"], sa_info["zone_name"],
                    sa_info["city"], sa_info["country"]
                )
                all_companies.extend(results)
            except Exception as e:
                tb = traceback.format_exc()
                print(f"  [{instance_id}] ERROR scraping '{sa_info['subarea_name']}': {e}")
                state.log_failure("Execution Engine — Company Discovery", {
                    "instance_id": f"Agent5-{sa_info['subarea_name']}",
                    "error": f"Scraping failed for subarea '{sa_info['subarea_name']}': {e}",
                    "traceback": tb
                })
        return all_companies

    def _on_active_change(delta: int):
        # The guard allows agents to run standalone without an orchestrator wrapper.
        # Fails silently instead of crashing when 'run_pipeline.py' is executed directly.
        if state.orchestrator is not None and state.orchestrator.metrics:
            _am = state.orchestrator.metrics.agents.get("5")
            if _am is not None:
                _am.change_active_instances(delta)
            else:
                print("[run_pipeline] WARNING: metrics key '5' not found — skipping change_active_instances for Agent 5")

    # Cap concurrent browser instances for resource safety
    effective_workers = min(K, max_scrapers)
    all_results, failures = fault_tolerant_dispatch(
        worker_fn=scraper_worker,
        batches=batches,
        agent_name="Agent 5 — Playwright Scraper",
        max_workers=effective_workers,
        on_active_change=_on_active_change,
    )

    # Log failures
    for f in failures:
        state.log_failure("Phase 5 — Lead Scraping", f)

    # FIX: Flatten list-of-lists from fault_tolerant_dispatch before deduplication.
    # scraper_worker returns a list[dict]; fault_tolerant_dispatch wraps each worker's
    # result as one element, so all_results is [[{...},{...}], [{...}]] not [{...},{...}].
    # The old code checked isinstance(item, dict) on the outer LIST, silently dropping
    # ALL leads.
    flat_results = []
    for batch_result in all_results:
        if isinstance(batch_result, list):
            flat_results.extend(batch_result)
        elif isinstance(batch_result, dict):
            flat_results.append(batch_result)

    # Global deduplication
    unique_companies = []
    seen = set()
    for item in flat_results:
        if isinstance(item, dict):
            norm_name = item.get("company_name", "").lower().strip()
            if norm_name and norm_name not in seen:
                seen.add(norm_name)
                unique_companies.append(item)

    state.scraped_companies = unique_companies
    print(f"\n  [Phase 5] Scraping completed. {len(unique_companies)} unique companies "
          f"(down from {len(flat_results)} total after flattening {len(all_results)} batches).")


# ═══════════════════════════════════════════════════════════════════
#  MAIN — Pipeline Entry Point
# ═══════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    state = PipelineState()

    print("\n" + "=" * 60)
    print("      MASTER AGENT AUTONOMOUS PARALLEL ORCHESTRATOR")
    print("=" * 60 + "\n")

    # ── Determine entry point based on CLI args ────────────────────

    if args.zones:
        # Direct Zone Mode — skip Phases 1-3
        direct_zones = [z.strip() for z in args.zones.split(",") if z.strip()]
        city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
        country = args.countries.split(",")[0].strip() if args.countries else "India"
        state.master_zone_registry[(city, country)] = direct_zones
        state.all_cities.append({"city": city, "country": country, "tier": 1})
        print(f"-> Direct Zone Mode: {len(direct_zones)} zones in {city}, {country}")
        print(f"   Zones: {direct_zones}")

    elif args.cities:
        # Direct City Mode — skip Phase 1 & 2
        cities = [c.strip() for c in args.cities.split(",") if c.strip()]
        country = args.countries.split(",")[0].strip() if args.countries else "India"
        for city_name in cities:
            state.all_cities.append({"city": city_name, "country": country, "tier": 1})
        print(f"-> Direct City Mode: {len(cities)} cities")

        # Run Phase 3
        phase_3_zone_finding(state)

    else:
        # Full Pipeline — all phases

        # Phase 1: GDP Ranking
        phase_1_gdp_ranking(state, args)

        # Phase 2: City Segmentation
        phase_2_city_segmentation(state)

        if not state.all_cities:
            print("[Error] No cities found after Phase 2. Exiting.")
            return

        # Phase 3: Zone Finding
        phase_3_zone_finding(state)

    # ── Phases 4 & 5 always run ────────────────────────────────────

    if not state.master_zone_registry:
        print("[Error] No zones found. Cannot proceed to Phase 4. Exiting.")
        return

    # Phase 4: Sub-Area Mapper
    phase_4_subarea_mapper(state)

    # Phase 4.5: Supabase Insert
    phase_4_5_supabase_insert(state, args.skip_supabase)

    # Phase 5: Lead Scraper
    phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers)

    # Phase 5.5: Supabase Leads Insert
    phase_5_5_supabase_insert_leads(state, args.skip_supabase)

    # ── Save final output ──────────────────────────────────────────

    state.finalize()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(project_root, "outputs")
    os.makedirs(out_dir, exist_ok=True)

    out_file = os.path.join(out_dir, f"pipeline_lead_results_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)

    # ── Final Report ───────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("      MASTER AGENT AUTONOMOUS PARALLEL ORCHESTRATOR — COMPLETED")
    print("=" * 60)
    state.summary()
    print(f"Total Companies Scraped  : {len(state.scraped_companies)}")
    print(f"Consolidated Leads Saved : {out_file}")

    if state.failures:
        print(f"\n  ⚠ DROPPED SLICES ({len(state.failures)}):")
        for fail in state.failures:
            print(f"    Phase: {fail.get('phase', '?')}")
            print(f"    Instance: {fail.get('instance_id', '?')}")
            print(f"    Error: {fail.get('error', '?')}")
            print(f"    ---")

    print("=" * 60 + "\n")

# --------------------------------Helper--------------------------------
# Add this anywhere in run_pipeline.py
import json
from pathlib import Path

def write_status(state, phase_id, status, progress, logs, output, elapsed, workers):
    status_file = Path(__file__).parent / "pipeline_status.json"
    current = {}
    if status_file.exists():
        with open(status_file) as f:
            current = json.load(f)
    current.setdefault("phases", {})[phase_id] = {
        "status": status, "progress": progress,
        "logs": logs, "output": output,
        "elapsed": elapsed, "workers": workers
    }
    current["global_counts"] = {
        "countries": len(state.gdp_ranked_countries),
        "cities":    len(state.all_cities),
        "zones":     sum(len(z) for z in state.master_zone_registry.values()),
        "leads":     len(state.scraped_companies)
    }
    current["done"] = False
    with open(status_file, "w") as f:
        json.dump(current, f)

# --------------------------------Helper end's------------------------------        




if __name__ == "__main__":
    main()