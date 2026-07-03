from supabase_client import get_countries

countries = get_countries()

print(len(countries))

print(countries[:5])