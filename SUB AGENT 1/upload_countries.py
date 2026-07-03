from supabase_client import supabase
from gdp_ranker import SOVEREIGN_STATES

rows = []

for country in SOVEREIGN_STATES:
    rows.append({
        "country_name": country["name"],
        "iso2": country["iso2"],
        "iso3": country["iso3"]
    })

response = supabase.table("countries").insert(rows).execute()

print(f"Inserted {len(rows)} countries successfully!")