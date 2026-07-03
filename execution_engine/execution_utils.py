import re
import logging
from config import IGNORE_KEYWORDS, CATEGORY_SCORE

log = logging.getLogger(__name__)


def extract_category(text: str) -> str:
    """Extract the highest matching category from the text block."""
    text_lower = text.lower()
    for keyword in CATEGORY_SCORE.keys():
        if keyword in text_lower:
            return keyword
    return ""


def calculate_priority(category: str) -> int:
    """Return priority score based on category."""
    return CATEGORY_SCORE.get(category, 1)


def clean_company_name(name: str, category: str) -> str:
    """Remove category text from company name and strip extra spaces."""
    if category:
        idx = name.lower().find(category)
        if idx != -1:
            name = name[:idx].strip()
    return " ".join(name.split())


def is_noise(name: str) -> bool:
    """Check if the company name contains ignored keywords."""
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in IGNORE_KEYWORDS)


def process_card_text(text: str, seen_companies: set) -> dict | None:
    """Parse a single Google Maps card, filter, and deduplicate."""
    if not text:
        return None

    lines = text.split("\n")
    if not lines:
        return None

    raw_name = lines[0].strip()
    if not raw_name:
        return None

    category = extract_category(text)
    company_name = clean_company_name(raw_name, category)

    if not company_name:
        return None

    normalized_name = company_name.lower().strip()

    if normalized_name in seen_companies:
        return None

    if is_noise(normalized_name):
        return None

    seen_companies.add(normalized_name)
    
    score = calculate_priority(category)

    return {
        "name": company_name,
        "category": category,
        "priority": score
    }