import logging
import time
from typing import TypedDict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from execution_worker import scrape_subarea
from supabase_execution import insert_execution_results, mark_subarea_processed

log = logging.getLogger(__name__)


class ExecutionState(TypedDict):
    subareas: List[dict]
    total_companies: int
    completed: int
    failed: int
    skipped: int


def node_load_subareas(state: ExecutionState) -> ExecutionState:
    from supabase_execution import get_unprocessed_subareas
    subareas = get_unprocessed_subareas()
    log.info(f"Loaded {len(subareas)} unprocessed subareas from Supabase.")
    return {
        **state,
        "subareas": subareas,
        "total_companies": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0
    }


def node_run_swarm(state: ExecutionState) -> ExecutionState:
    from config import EXECUTION_ENGINE_WORKERS
    subareas = state["subareas"]
    total_companies = state["total_companies"]
    completed = state["completed"]
    failed = state["failed"]
    skipped = state["skipped"]

    workers = min(EXECUTION_ENGINE_WORKERS, len(subareas)) if subareas else 1

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                process_single_subarea, 
                subarea
            ): subarea for subarea in subareas
        }

        for future in as_completed(futures):
            subarea = futures[future]
            sub_name = subarea.get("subarea_name", "Unknown")
            try:
                result = future.result()
                total_companies += result.get("companies_scraped", 0)
                if result["status"] == "SUCCESS":
                    completed += 1
                elif result["status"] == "SKIPPED":
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Future crashed for {sub_name}: {e}")
                failed += 1

    return {
        **state,
        "total_companies": total_companies,
        "completed": completed,
        "failed": failed,
        "skipped": skipped
    }


def process_single_subarea(subarea: dict) -> dict:
    """Isolated worker logic for a single subarea."""
    subarea_name = subarea.get("subarea_name", "").strip()
    zone_name = subarea.get("zone_name", "").strip()
    city_name = subarea.get("city", "").strip()
    country_name = subarea.get("country", "").strip()

    if not subarea_name:
        return {"status": "SKIPPED", "companies_scraped": 0}

    log.info(f"Processing Subarea: {subarea_name} ({zone_name})")

    try:
        companies = scrape_subarea(subarea_name, zone_name, city_name, country_name)
        
        if not companies:
            log.warning(f"[{subarea_name}] No valid companies scraped. Marking as processed to avoid loop.")
            mark_subarea_processed(subarea_name, zone_name)
            return {"status": "SUCCESS", "companies_scraped": 0}

        # Sort by priority descending before inserting
        companies.sort(key=lambda x: x.get("priority", 1), reverse=True)

        db_stats = insert_execution_results(companies)
        log.info(f"[{subarea_name}] DB Insert -> Inserted: {db_stats['inserted']}, Skipped: {db_stats['skipped']}, Failed: {db_stats['failed']}")

        # Checkpoint: Mark as processed ONLY if we successfully handled it
        mark_success = mark_subarea_processed(subarea_name, zone_name)
        
        if mark_success:
            return {"status": "SUCCESS", "companies_scraped": db_stats["inserted"]}
        else:
            return {"status": "FAILED", "companies_scraped": 0}

    except Exception as e:
        log.error(f"[{subarea_name}] Unhandled exception in worker: {e}")
        return {"status": "FAILED", "companies_scraped": 0}
    finally:
        # Polite delay between subareas to ease network load
        time.sleep(2)