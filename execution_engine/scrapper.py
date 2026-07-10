from playwright.sync_api import sync_playwright
import json

search_query = input("Enter search query: ")

companies = []

with sync_playwright() as p:

    # Launch browser
    browser = p.chromium.launch(
        headless=False,
        slow_mo=500
    )

    # Create page
    page = browser.new_page()

    # Open Google Maps directly
    maps_url = f"https://www.google.com/maps/search/{search_query}"

    page.goto(
        maps_url,
        timeout=120000,
        wait_until="domcontentloaded"
    )

    print("Google Maps opened successfully!")

    # Wait for results to appear
    page.wait_for_timeout(20000)

    # Keep browser open for debugging
    input("\nCheck if business cards are visible, then press Enter...\n")

    # Scroll slowly multiple times
    for _ in range(5):

        page.mouse.wheel(0, 4000)

        page.wait_for_timeout(3000)

    # Select business cards
    cards = page.locator("div.Nv2PK")

    count = cards.count()

    print(f"\nFound {count} cards\n")

    for i in range(count):

        try:

            text = cards.nth(i).text_content()

            print(f"\nCARD {i}:\n{text}")

            if text:

                lines = text.split("\n")

                company_name = lines[0].strip()

                if company_name not in companies:

                    companies.append(company_name)

        except Exception as e:

            print("Error:", e)
