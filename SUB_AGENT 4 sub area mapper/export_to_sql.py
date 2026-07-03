import json
import os
import logging
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

REQUIRED_KEYS = {"input", "results"}


def export_to_sql(json_file: str) -> None:
    """Read a JSON file from the outputs folder and upsert to Supabase."""
    json_path = os.path.join("outputs", json_file)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in file")
            
        data = json.loads(content[start:end])
    except FileNotFoundError:
        log.error(f"File not found: {json_path}")
        return
    except Exception as e:
        log.error(f"Error reading or parsing JSON: {e}")
        return

    if not REQUIRED_KEYS.issubset(data.keys()):
        log.error(f"Invalid data format. Missing keys: {REQUIRED_KEYS - data.keys()}")
        return

    zone_name = data["input"].get("zone_name", "Unknown")
    country = data["input"].get("country", "Unknown")

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    for item in data["results"]:
        row = {
            "zone_name": zone_name,
            "subarea_name": item.get("subarea_name"),
            "parent_zone": item.get("parent_zone"),
            "business_volume": item.get("business_volume"),
            "city": item.get("city"),
            "country": country,
            "source_url": item.get("source_url"),
            "retrieved_at": item.get("retrieved_at"),
            "status": item.get("status")
        }

        try:
            supabase.table("subareas").insert(row).execute()
            inserted_count += 1
            log.info(f"Inserted: {row['subarea_name']}")
        except Exception as e:
            err_str = str(e)
            if "23505" in err_str or "duplicate" in err_str.lower():
                log.warning(f"Skipped duplicate: {row['subarea_name']}")
                skipped_count += 1
            else:
                log.error(f"Failed to insert {row['subarea_name']}: {e}")
                failed_count += 1

    log.info(f"Export complete for {zone_name}. Inserted: {inserted_count}, Skipped: {skipped_count}, Failed: {failed_count}")


if __name__ == "__main__":
    json_file = input("Enter JSON file name: ").strip()
    export_to_sql(json_file)