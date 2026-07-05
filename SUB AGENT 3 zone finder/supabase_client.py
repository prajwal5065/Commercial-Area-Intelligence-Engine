
"""
supabase_client.py — Shared Supabase helper layer
Used by Sub-Agent 2 (Company Finder) and Sub-Agent 3 (Zone Finder).
"""

import os
import time
import logging
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════════════════
#  ERROR CLASSIFIERS
# ═══════════════════════════════════════════════════════════════════

def _is_retryable(e: Exception) -> bool:
    msg = str(e).lower()
    signals = [
        "429", "rate_limit", "timeout", "timed out",
        "connection reset", "server disconnected",
        "network", "502", "503", "504", "temporary",
    ]
    return any(s in msg for s in signals)


def _is_duplicate(e: Exception) -> bool:
    msg = str(e)
    return "23505" in msg or "duplicate key" in msg.lower()


def _supabase_op(label: str, fn, max_attempts: int = 3):
    """
    Execute a Supabase callable fn() with retry on transient errors.
    Silently skips duplicates. Returns response or None.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if _is_duplicate(e):
                log.info(f"Skipped duplicate: {label}")
                return None
            if _is_retryable(e) and attempt < max_attempts - 1:
                wait = 2 ** attempt
                log.warning(
                    f"Transient error [{label}] attempt {attempt + 1}/{max_attempts}, "
                    f"retrying in {wait}s — {e}"
                )
                time.sleep(wait)
                continue
            log.error(f"Permanent error [{label}]: {e}")
            return None
    log.error(f"Gave up [{label}] after {max_attempts} attempts.")
    return None


# ═══════════════════════════════════════════════════════════════════
#  COUNTRIES
# ═══════════════════════════════════════════════════════════════════

def get_countries() -> list:
    response = (
        supabase
        .table("countries")
        .select("*")
        .order("country_name")
        .execute()
    )
    return response.data


# ═══════════════════════════════════════════════════════════════════
#  CITIES  (read by Sub-Agent 3)
# ═══════════════════════════════════════════════════════════════════

def get_cities(country_name: str = None) -> list:
    """
    Return all cities from the cities table ordered by city_name.
    Optionally filter by country_name.
    Expected columns: id, city_name, country
    """
    q = supabase.table("cities").select("*").order("city_name")
    if country_name:
        q = q.eq("country", country_name)
    response = q.execute()
    return response.data


# ═══════════════════════════════════════════════════════════════════
#  COMPANIES  (Sub-Agent 2)
# ═══════════════════════════════════════════════════════════════════

def insert_company(
    company_name: str,
    country_name: str,
    city_name,
    zone_name,
    category: str,
    priority: int,
    source_url: str,
):
    """Upsert a company record. Silently skips duplicates."""
    data = {
        "company_name": company_name,
        "country_name": country_name,
        "city_name":    city_name,
        "zone_name":    zone_name,
        "category":     category,
        "priority":     priority,
        "source_url":   source_url,
    }
    return _supabase_op(
        company_name,
        lambda: supabase.table("companies").upsert(data, on_conflict="company_name").execute(),
    )


def company_exists(company_name: str) -> bool:
    try:
        resp = (
            supabase
            .table("companies")
            .select("id")
            .eq("company_name", company_name)
            .execute()
        )
        return len(resp.data) > 0
    except Exception as e:
        log.error(f"company_exists error for '{company_name}': {e}")
        return False


def get_zone_table_name(city_name: str) -> str:
    """
    Generate a dynamic table name based on the city name to avoid PGRST205 (table not found).
    Example: "pune" -> "zones_pune", "Mumbai" -> "zones_mumbai", "Bhopal" -> "zones_bhopal"
    """
    safe_city = "".join(c if c.isalnum() else "_" for c in city_name).lower()
    return f"zones_{safe_city}"


# ═══════════════════════════════════════════════════════════════════
#  ZONES  (Sub-Agent 3)
# ═══════════════════════════════════════════════════════════════════

def upsert_zone(
    zone_name: str,
    city_name: str,
    country_name: str,
    business_count,
    count_source: str,
    source_url: str,
    rank: int = None,
):
    """
    Upsert a zone record into the zones table.
    Conflict target: (zone_name, city_name).
    Silently skips duplicates. Retries on transient errors.
    """
    data = {
        "zone_name":      zone_name,
        "city_name":      city_name,
        "country_name":   country_name,
        "business_count": business_count,
        "count_source":   count_source,
        "source_url":     source_url,
        "rank":           rank,
    }
    return _supabase_op(
        f"{zone_name} / {city_name}",
        lambda: (
            supabase
            .table("zones")
            .upsert(data, on_conflict="zone_name,city_name")
            .execute()
        ),
    )


# Alias kept for backward compatibility
def insert_zone(
    zone_name: str,
    city_name: str,
    country_name: str,
    business_count,
    count_source: str,
    source_url: str,
    rank: int = None,
):
    return upsert_zone(
        zone_name=zone_name,
        city_name=city_name,
        country_name=country_name,
        business_count=business_count,
        count_source=count_source,
        source_url=source_url,
        rank=rank,
    )


def zone_exists(zone_name: str, city_name: str) -> bool:
    try:
        resp = (
            supabase
            .table("zones")
            .select("id")
            .eq("zone_name", zone_name)
            .eq("city_name", city_name)
            .execute()
        )
        return len(resp.data) > 0
    except Exception as e:
        log.error(f"zone_exists error for '{zone_name}' / '{city_name}': {e}")
        return False
