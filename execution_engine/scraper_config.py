import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# ENVIRONMENT CONFIGURATION
# ==========================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
EXECUTION_ENGINE_WORKERS = int(os.getenv("EXECUTION_ENGINE_WORKERS", "1"))

if not SUPABASE_URL or not SUPABASE_KEY:
    import logging as _logging
    _logging.warning(
        "execution_engine/config.py: SUPABASE_URL or SUPABASE_KEY missing in .env — "
        "Supabase persistence will be disabled. Scraping will still run."
    )  # FIX: was hard raise EnvironmentError, which crashed scraper threads silently

# ==========================================
# PLAYWRIGHT CONFIGURATION
# ==========================================

PLAYWRIGHT_HEADLESS = True
PLAYWRIGHT_SLOW_MO = 200
PLAYWRIGHT_TIMEOUT = 60000
MAPS_LOAD_WAIT = 15000
SCROLL_ITERATIONS = 15
SCROLL_DELAY_MS = 2000

# ==========================================
# SCRAPING RULES
# ==========================================

IGNORE_KEYWORDS = [
    "salon", "spa", "restaurant", "cafe", "coffee",
    "bar", "pub", "brewpub", "hotel", "resort",
    "hostel", "hospital", "clinic", "medical",
    "gym", "fitness", "school", "college",
    "university", "mall", "shopping", "supermarket",
    "grocery", "bakery", "sweet", "real estate",
    "property", "housing", "apartment"
]

CATEGORY_SCORE = {
    "software company": 10,
    "it services": 10,
    "technology company": 10,
    "computer support and services": 10,
    "computer hardware company": 9,
    "engineering consultant": 9,
    "engineering company": 9,
    "consultant": 9,
    "automation company": 9,
    "ai company": 9,
    "cloud services": 9,
    "business management consultant": 8,
    "corporate office": 8,
    "marketing agency": 8,
    "industrial equipment supplier": 8,
    "electronics company": 8,
    "telecommunications service provider": 8,
    "logistics service": 8,
    "manufacturer": 7,
    "oil & natural gas company": 7,
    "coworking space": 7,
    "business center": 7,
    "technology park": 7,
    "computer store": 7,
    "research and product development": 6,
    "building firm": 6,
    "construction company": 6,
    "pharmaceutical company": 5,
    "metal fabricator": 5,
    "cleaning services": 5,
    "chartered accountant": 4,
    "advertising agency": 4,
    "travel agency": 3,
    "event management company": 3,
    "transportation service": 3
}

# ==========================================
# RETRY CONFIGURATION
# ==========================================

MAX_RETRIES = 3
RETRY_DELAY_BASE = 2
