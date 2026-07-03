from supabase import create_client
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# -------------------------------------------------
# Read all countries
# -------------------------------------------------
def get_countries():

    response = (
        supabase
        .table("countries")
        .select("*")
        .order("country_name")
        .execute()
    )

    return response.data


# -------------------------------------------------
# Update GDP details for one country
# -------------------------------------------------
def update_country_gdp(record):

    response = (
        supabase
        .table("countries")
        .update({
            "nominal_gdp_usd": record["nominal_gdp_usd"],
            "per_capita_usd": record["per_capita_usd"],
            "gdp_rank": record["gdp_rank"],
            "data_tier": record["data_tier"],
            "source_url": record["source_url"],
            "retrieved_at": record["retrieved_at"]
        })
        .eq("iso3", record["iso_code"])
        .execute()
    )

    return response