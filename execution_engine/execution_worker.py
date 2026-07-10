import time
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from execution_utils import process_card_text
from scraper_config import (
    PLAYWRIGHT_HEADLESS, PLAYWRIGHT_SLOW_MO, PLAYWRIGHT_TIMEOUT,
    MAPS_LOAD_WAIT, SCROLL_ITERATIONS, SCROLL_DELAY_MS,
    MAX_RETRIES, RETRY_DELAY_BASE
)

log = logging.getLogger(__name__)


def scrape_subarea(subarea_name: str, zone_name: str, city_name: str, country_name: str) -> list:
    """Execute Playwright to scrape Google Maps for a specific subarea."""
    search_query = f"{subarea_name} companies"
    maps_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
    
    companies = []
    seen_companies = set()

    for attempt in range(MAX_RETRIES):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=PLAYWRIGHT_HEADLESS,
                    slow_mo=PLAYWRIGHT_SLOW_MO
                )
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                log.info(f"[{subarea_name}] Navigating to Google Maps...")
                page.goto(maps_url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")
                
                # Wait for initial results panel to load
                try:
                    page.wait_for_selector("div.Nv2PK", timeout=MAPS_LOAD_WAIT)
                except PlaywrightTimeout:
                    log.warning(f"[{subarea_name}] Timed out waiting for cards. Retrying...")
                    browser.close()
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_BASE ** (attempt + 1))
                        continue
                    return []

                # Scroll to load more results
                for _ in range(SCROLL_ITERATIONS):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(SCROLL_DELAY_MS)

                # Extract cards
                cards = page.locator("div.Nv2PK")
                count = cards.count()
                log.info(f"[{subarea_name}] Found {count} cards on Google Maps.")

                for i in range(count):
                    try:
                        text = cards.nth(i).text_content()
                        processed = process_card_text(text, seen_companies)
                        
                        if processed:
                            companies.append({
                                "subarea_name": subarea_name,
                                "zone_name": zone_name,
                                "city_name": city_name,
                                "country_name": country_name,
                                "company_name": processed["name"],
                                "category": processed["category"],
                                "priority": processed["priority"]
                            })
                    except Exception as card_err:
                        log.debug(f"[{subarea_name}] Error parsing card {i}: {card_err}")

                browser.close()
                return companies

        except Exception as e:
            log.error(f"[{subarea_name}] Playwright error on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE ** (attempt + 1))
            else:
                log.error(f"[{subarea_name}] Max retries reached. Skipping.")
                return []

    return companies
