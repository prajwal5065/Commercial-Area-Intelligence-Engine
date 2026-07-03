import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from main import process_zone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def worker(zone: str, city: str, country: str) -> dict:
    """Wrapper to process a single zone and catch unhandled exceptions."""
    try:
        result = process_zone(zone, city, country)
        return result
    except Exception as e:
        log.error(f"Unhandled exception for {zone}: {e}")
        return {"status": "ERROR", "zone": zone, "path": None}
    finally:
        # Polite delay to prevent hammering the API sequentially
        time.sleep(2)


def run_swarm(zones: list, city: str, country: str) -> None:
    """Execute parallel processing for a list of zones and log the summary."""
    successful = 0
    failed = 0
    skipped = 0
    total = len(zones)

    with ThreadPoolExecutor(max_workers=min(total, 1)) as executor:
        futures = {
            executor.submit(worker, zone, city, country): zone
            for zone in zones
        }

        for future in as_completed(futures):
            zone = futures[future]
            try:
                result = future.result()
                status = result.get("status", "ERROR")
                if status == "SUCCESS":
                    successful += 1
                elif status == "ERROR":
                    failed += 1
                else:
                    skipped += 1
            except Exception as e:
                log.error(f"Future failed for {zone}: {e}")
                failed += 1

    log.info("=" * 40)
    log.info("Swarm Execution Summary")
    log.info(f"Total     : {total}")
    log.info(f"Successful: {successful}")
    log.info(f"Failed    : {failed}")
    log.info(f"Skipped   : {skipped}")
    log.info("=" * 40)


if __name__ == "__main__":
    zones = [
        "BKC",
        "Powai",
        "Andheri"
    ]
    
    run_swarm(zones, "Mumbai", "India")