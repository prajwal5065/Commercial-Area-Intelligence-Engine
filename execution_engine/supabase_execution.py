import time
import logging
from datetime import datetime
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, MAX_RETRIES, RETRY_DELAY_BASE

log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _is_duplicate(e: Exception) -> bool:
    msg = str(e)
    return "23505" in msg or "duplicate" in msg.lower()


def _is_retryable(e: Exception) -> bool:
    msg = str(e).lower()
    return any(sig in msg for sig in ["429", "timeout", "network", "502", "503", "504"])


def get_unprocessed_subareas() -> list:
    """Fetch subareas that have not been scraped yet."""
    for attempt in range(MAX_RETRIES):
        try:
            response = (
                supabase
                .table("subareas")
                .select("subarea_name, zone_name, city, country")
                .is_("is_scraped", "false")
                .execute()
            )
            return response.data
        except Exception as e:
            if _is_retryable(e) and attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY_BASE ** attempt
                log.warning(f"Supabase fetch retry {attempt + 1}/{MAX_RETRIES} waiting {wait}s")
                time.sleep(wait)
            else:
                log.error(f"Failed to fetch unprocessed subareas: {e}")
                return []
    return []


def insert_execution_results(records: list) -> dict:
    """Insert scraped companies into execution_results table."""
    stats = {"inserted": 0, "skipped": 0, "failed": 0}
    if not records:
        return stats

    for record in records:
        row = {
            "subarea_name": record.get("subarea_name"),
            "zone_name": record.get("zone_name"),
            "city_name": record.get("city_name"),
            "country_name": record.get("country_name"),
            "company_name": record.get("company_name"),
            "category": record.get("category"),
            "priority": record.get("priority"),
            "created_at": datetime.now().isoformat()
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                supabase.table("execution_results").insert(row).execute()
                stats["inserted"] += 1
                break
            except Exception as e:
                if _is_duplicate(e):
                    stats["skipped"] += 1
                    break
                elif _is_retryable(e) and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_BASE ** attempt)
                else:
                    log.error(f"Failed to insert {row.get('company_name')}: {e}")
                    stats["failed"] += 1
    return stats


def mark_subarea_processed(subarea_name: str, zone_name: str) -> bool:
    """Mark a subarea as scraped to prevent re-processing."""
    for attempt in range(MAX_RETRIES):
        try:
            supabase.table("subareas").update({"is_scraped": True}).eq("subarea_name", subarea_name).eq("zone_name", zone_name).execute()
            return True
        except Exception as e:
            if _is_retryable(e) and attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE ** attempt)
            else:
                log.error(f"Failed to mark {subarea_name} as processed: {e}")
                return False
    return False