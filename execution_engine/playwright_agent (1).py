from playwright.sync_api import sync_playwright
import json
from datetime import datetime

search_query = input("Enter search query: ")
companies = []

# =========================
# EDGE CASE HANDLING BLOCK
# =========================

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
    # Top Priority IT / Software
    "software company": 10,
    "it services": 10,
    "technology company": 10,
    "computer support and services": 10,

    # High Priority Tech
    "computer hardware company": 9,
    "engineering consultant": 9,
    "engineering company": 9,
    "consultant": 9,
    "automation company": 9,
    "ai company": 9,
    "cloud services": 9,

    # Business / Corporate
    "business management consultant": 8,
    "corporate office": 8,
    "marketing agency": 8,
    "industrial equipment supplier": 8,
    "electronics company": 8,
    "telecommunications service provider": 8,
    "logistics service": 8,

    # Industrial
    "manufacturer": 7,
    "oil & natural gas company": 7,
    "coworking space": 7,
    "business center": 7,
    "technology park": 7,
    "computer store": 7,

    # Medium Priority
    "research and product development": 6,
    "building firm": 6,
    "construction company": 6,

    # Lower Priority
    "pharmaceutical company": 5,
    "metal fabricator": 5,
    "cleaning services": 5,

    # Low Priority
    "chartered accountant": 4,
    "advertising agency": 4,

    # Very Low Priority
    "travel agency": 3,
    "event management company": 3,
    "transportation service": 3
}

seen_companies = set()

duplicates_removed = 0
noise_removed = 0

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
        slow_mo=500
    )

    page = browser.new_page()

    maps_url = f"https://www.google.com/maps/search/{search_query}"
    print("SEARCH QUERY =", search_query)
    print("MAP URL =", maps_url)
    page.goto(
        maps_url,
        timeout=120000,
        wait_until="domcontentloaded"
    )

    print("Google Maps opened successfully!")

    page.wait_for_timeout(20000)

    input("\nCheck if business cards are visible, then press Enter...\n")

    try:
        page.locator("div.Nv2PK").first.hover()
    except Exception:
        pass

    for _ in range(20):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(3000)

    cards = page.locator("div.Nv2PK")
    count = cards.count()

    print(f"\nFound {count} cards\n")

    for i in range(count):

        try:
            text = cards.nth(i).text_content()

            if not text:
                continue

            try:
                print(f"\nCARD {i}:")
                print(text.encode("ascii", "ignore").decode("ascii"))
            except Exception:
                pass

            text_lower = text.lower()

            # =========================
            # CATEGORY EXTRACTION
            # =========================

            category = ""

            for keyword in CATEGORY_SCORE.keys():
                if keyword in text_lower:
                    category = keyword
                    break

            # =========================
            # COMPANY NAME EXTRACTION
            # =========================

            company_name = text.split("\n")[0].strip()

            # Remove category text from company name
            if category:
                idx = company_name.lower().find(category)

                if idx != -1:
                    company_name = company_name[:idx].strip()

            # Remove extra spaces
            company_name = " ".join(company_name.split())

            if not company_name:
                continue

            # =========================
            # PRIORITY SCORING
            # =========================

            score = CATEGORY_SCORE.get(category, 1)

            normalized_name = company_name.lower().strip()

            # =========================
            # DUPLICATE HANDLING
            # =========================

            if normalized_name in seen_companies:
                duplicates_removed += 1
                continue

            seen_companies.add(normalized_name)

            # =========================
            # NOISE FILTERING
            # =========================

            if any(keyword in normalized_name for keyword in IGNORE_KEYWORDS):
                noise_removed += 1
                continue

            companies.append({
                "name": company_name,
                "category": category,
                "priority": score
            })

        except Exception as e:
            print("Error:", e)

    browser.close()

print("\n========================")
print("SCRAPING SUMMARY")
print("========================")
print(f"Duplicates removed: {duplicates_removed}")
print(f"Noise removed: {noise_removed}")
print(f"Final companies: {len(companies)}")
print("========================\n")

# =========================
# SORT BY PRIORITY
# =========================

companies.sort(
    key=lambda x: x["priority"],
    reverse=False
)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

output_file = (
    f"{search_query.replace(' ', '_')}_{timestamp}_companies.json"
)

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(companies, f, indent=4, ensure_ascii=False)

print(f"\n✅ Success! Saved {len(companies)} companies to {output_file}")
