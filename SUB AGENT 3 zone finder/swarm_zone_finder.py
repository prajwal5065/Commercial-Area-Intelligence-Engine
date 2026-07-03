import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict, List

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from supabase_client import get_cities
from zone_finders_code import process_city

load_dotenv()

# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)

# --------------------------------------------------
# Agent State
# --------------------------------------------------

class ZoneAgentState(TypedDict):
    cities: List[dict]
    batches: List[List[dict]]
    processed: int
    failed: int

# --------------------------------------------------
# Node 1 : Load Cities
# --------------------------------------------------

def node_load_cities(state: ZoneAgentState) -> ZoneAgentState:
    cities = get_cities()
    log.info(f"Loaded {len(cities)} cities from Supabase")
    return {
        "cities":    cities,
        "batches":   [],
        "processed": 0,
        "failed":    0,
    }

# --------------------------------------------------
# Node 2 : Create Batches
# --------------------------------------------------

def node_create_batches(state: ZoneAgentState) -> ZoneAgentState:
    cities     = state["cities"]
    batch_size = 10
    batches    = [
        cities[i:i + batch_size]
        for i in range(0, len(cities), batch_size)
    ]
    log.info(f"Created {len(batches)} batches of up to {batch_size} cities each")
    return {
        **state,
        "batches": batches,
    }

# --------------------------------------------------
# Worker — one city
# --------------------------------------------------

def worker(city_row: dict) -> dict:
    """
    Process one city row from Supabase.
    Expected keys: city_name, country_name
    Returns dict with status info.
    """
    city_name    = city_row.get("city_name", "").strip()
    country_name = city_row.get("country_name", "").strip()

    if not city_name or not country_name:
        log.warning(f"Skipping row with missing city/country: {city_row}")
        return {"city": city_name, "status": "SKIPPED", "zones": 0}

    try:
        data = process_city(city_name, country_name)
        zones_found = len(data.get("zones", []))
        log.info(f"Worker done: {city_name} — {zones_found} zones")
        return {"city": city_name, "status": data.get("status", "SUCCESS"), "zones": zones_found}
    except Exception as e:
        log.error(f"Worker error for {city_name}: {e}")
        return {"city": city_name, "status": "ERROR", "zones": 0}
    finally:
        # Polite delay between cities to prevent compounding API rate limits
        time.sleep(3)

# --------------------------------------------------
# Process one batch
# --------------------------------------------------

def process_batch(batch: list, max_workers: int = 1) -> dict:
    log.info(f"Batch started: {len(batch)} cities, {max_workers} workers")
    processed = 0
    failed    = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, city_row): city_row for city_row in batch}
        for future in as_completed(futures):
            city_row = futures[future]
            try:
                result = future.result()
                if result["status"] in ("SUCCESS", "NO_ZONES"):
                    processed += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Future raised for {city_row}: {e}")
                failed += 1

    log.info(f"Batch finished: {processed} ok, {failed} failed")
    return {"processed": processed, "failed": failed}

# --------------------------------------------------
# Node 3 : Run Swarm
# --------------------------------------------------

def node_run_swarm(state: ZoneAgentState) -> ZoneAgentState:
    batches = state["batches"]
    processed = 0
    failed = 0

    # Run only ONE city at a time to avoid Groq rate limits
    max_workers = 1

    for i, batch in enumerate(batches):
        log.info(f"Starting batch {i + 1}/{len(batches)}")

        try:
            result = process_batch(batch, max_workers=max_workers)

            processed += result["processed"]
            failed += result["failed"]

            log.info(
                f"Batch {i + 1}/{len(batches)} complete — "
                f"cumulative: {processed} processed, {failed} failed"
            )

        except Exception as e:
            log.error(f"Batch {i + 1} raised an unexpected error: {e}")
            failed += len(batch)

        # Small delay before next batch
        if i < len(batches) - 1:
            time.sleep(5)

    log.info(
        f"All batches done — total processed: {processed}, total failed: {failed}"
    )

    return {
        **state,
        "processed": processed,
        "failed": failed,
    }

# --------------------------------------------------
# Build LangGraph
# --------------------------------------------------

graph = StateGraph(ZoneAgentState)

graph.add_node("load_cities",    node_load_cities)
graph.add_node("create_batches", node_create_batches)
graph.add_node("run_swarm",      node_run_swarm)

graph.set_entry_point("load_cities")

graph.add_edge("load_cities",    "create_batches")
graph.add_edge("create_batches", "run_swarm")
graph.add_edge("run_swarm",      END)

agent = graph.compile()

# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("=" * 60)
    print("SUB AGENT 3 - ZONE FINDER")
    print("=" * 60)

    initial_state = {
        "cities":    [],
        "batches":   [],
        "processed": 0,
        "failed":    0,
    }

    result = agent.invoke(initial_state)

    print("\nFinished!")
    print(f"Cities Loaded  : {len(result['cities'])}")
    print(f"Swarm Batches  : {len(result['batches'])}")
    print(f"Processed      : {result['processed']}")
    print(f"Failed         : {result['failed']}")


if __name__ == "__main__":
    main()