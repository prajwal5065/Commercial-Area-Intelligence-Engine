from supabase import create_client
from dotenv import load_dotenv
import os
import time
import logging

load_dotenv()

log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------
# Read all countries
# ----------------------------
def get_countries():
    response = (
        supabase
        .table("countries")
        .select("*")
        .order("country_name")
        .execute()
    )
    return response.data


# ----------------------------
# Classify whether an exception is retryable
# ----------------------------
def _is_retryable(e: Exception) -> bool:
    msg = str(e).lower()
    retryable_signals = [
        "429",
        "rate_limit",
        "timeout",
        "timed out",
        "connection reset",
        "server disconnected",
        "network",
        "502",
        "503",
        "504",
        "temporary",
    ]
    return any(signal in msg for signal in retryable_signals)


def _is_duplicate(e: Exception) -> bool:
    msg = str(e)
    return "23505" in msg or "duplicate key" in msg.lower()


# ----------------------------
# Check whether a city already exists
# ----------------------------
def city_exists(city_name, country_name):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("cities")
                .select("id")
                .eq("city_name", city_name)
                .eq("country_name", country_name)
                .execute()
            )
            return len(response.data) > 0

        except Exception as e:
            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error checking city '{city_name}, {country_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            log.error(f"Permanent error checking city '{city_name}, {country_name}': {e}")
            return False

    log.error(f"Gave up checking city '{city_name}, {country_name}' after {max_attempts} attempts.")
    return False


# ----------------------------
# Insert a city (duplicate-safe)
# ----------------------------
def insert_city(city_name, country_name):
    if city_exists(city_name, country_name):
        return None

    city_data = {
        "city_name": city_name,
        "country_name": country_name,
    }

    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("cities")
                .insert(city_data)
                .execute()
            )
            return response

        except Exception as e:
            if _is_duplicate(e):
                log.info(f"Skipped duplicate city: {city_name}, {country_name}")
                return None

            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error inserting city '{city_name}, {country_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            log.error(f"Permanent error inserting city '{city_name}, {country_name}': {e}")
            return None

    log.error(f"Gave up inserting city '{city_name}, {country_name}' after {max_attempts} attempts.")
    return None


# ----------------------------
# Insert / upsert one company
# ----------------------------
def insert_company(
    company_name,
    country_name,
    city_name,
    zone_name,
    category,
    priority,
    source_url,
):
    company_data = {
        "company_name": company_name,
        "country_name": country_name,
        "city_name": city_name,
        "zone_name": zone_name,
        "category": category,
        "priority": priority,
        "source_url": source_url,
    }

    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("companies")
                .upsert(company_data, on_conflict="company_name")
                .execute()
            )
            return response

        except Exception as e:
            if _is_duplicate(e):
                log.info(f"Skipped duplicate: {company_name}")
                return None

            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error saving '{company_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            # Non-retryable, non-duplicate — log once and bail
            log.error(f"Permanent error saving '{company_name}': {e}")
            return None

    log.error(f"Gave up saving '{company_name}' after {max_attempts} attempts.")
    return None
# -------------------------------------------------
# Upsert Zone
# -------------------------------------------------
def upsert_zone(
    zone_name: str,
    city_name: str,
    country_name: str,
    business_count,
    count_source: str,
    source_url: str,
    rank: int = None,
):
    zone_data = {
        "zone_name": zone_name,
        "city_name": city_name,
        "country_name": country_name,
        "business_count": business_count,
        "count_source": count_source,
        "source_url": source_url,
        "rank": rank,
    }

    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("zones")
                .upsert(zone_data, on_conflict="zone_name,city_name")
                .execute()
            )
            return response

        except Exception as e:
            if _is_duplicate(e):
                log.info(f"Skipped duplicate zone: {zone_name}")
                return None

            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error saving zone '{zone_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            log.error(f"Permanent error saving zone '{zone_name}': {e}")
            return None

    log.error(f"Gave up saving zone '{zone_name}' after {max_attempts} attempts.")
    return None

# ----------------------------
# Check whether company already exists
# ----------------------------
def company_exists(company_name):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("companies")
                .select("id")
                .eq("company_name", company_name)
                .execute()
            )
            return len(response.data) > 0

        except Exception as e:
            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error checking '{company_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            log.error(f"Permanent error checking '{company_name}': {e}")
            return False

    log.error(f"Gave up checking '{company_name}' after {max_attempts} attempts.")
    return False


# ----------------------------
# Check whether zone already exists
# ----------------------------
def zone_exists(zone_name, city_name):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = (
                supabase
                .table("zones")
                .select("id")
                .eq("zone_name", zone_name)
                .eq("city_name", city_name)
                .execute()
            )
            return len(response.data) > 0

        except Exception as e:
            if _is_retryable(e):
                wait = 2 ** attempt
                log.warning(
                    f"Transient error checking zone '{zone_name}' "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue

            log.error(f"Permanent error checking zone '{zone_name}': {e}")
            return False

    log.error(f"Gave up checking zone '{zone_name}' after {max_attempts} attempts.")
    return False