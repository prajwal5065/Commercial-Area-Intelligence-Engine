import os
import logging
import json
import time
from typing import TypedDict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

from supabase_client import (
    get_countries,
    insert_company,
    company_exists,
    insert_city,
)

load_dotenv()

# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)

# --------------------------------------------------
# LLM
# --------------------------------------------------

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY")
)

# --------------------------------------------------
# Agent State
# --------------------------------------------------

class AgentState(TypedDict):
    countries: List[dict]
    batches: List[List[dict]]
    processed: int

# --------------------------------------------------
# Node 1 : Load Countries
# --------------------------------------------------

def node_load_countries(state: AgentState):
    countries = get_countries()
    log.info(f"Loaded {len(countries)} countries from Supabase")
    return {
        "countries": countries,
        "batches": [],
        "processed": 0
    }

# --------------------------------------------------
# Node 2 : Create Swarm Batches
# --------------------------------------------------

def node_create_batches(state: AgentState):
    countries = state["countries"]
    batch_size = 20
    batches = [
        countries[i:i + batch_size]
        for i in range(0, len(countries), batch_size)
    ]
    log.info(f"Created {len(batches)} swarm batches of up to {batch_size} countries each")
    return {
        **state,
        "batches": batches
    }

# --------------------------------------------------
# Prompt builder
# --------------------------------------------------

def get_company_prompt(country_name):
    return f"""
You are a business intelligence analyst.

Return the top 10 largest companies headquartered in {country_name}.

For each company, include the headquarters city.

Return ONLY valid JSON.

Format:

[
  {{
    "company_name": "",
    "industry": "",
    "website": "",
    "city_name": ""
  }}
]

No markdown.
No explanation.
No extra text.
"""

# --------------------------------------------------
# Save companies for one country
# --------------------------------------------------

def save_companies(country_name, companies):
    for company in companies:
        try:
            city_name = company.get("city_name", "").strip()
            
            # Insert city first if provided
            if city_name:
                insert_city(city_name=city_name, country_name=country_name)
            
            insert_company(
                company_name=company.get("company_name", "").strip(),
                country_name=country_name,
                city_name=city_name if city_name else None,
                zone_name=None,
                category=company.get("industry", ""),
                priority=1,
                source_url=company.get("website", "")
            )
        except Exception as e:
            log.error(f"Unexpected error saving '{company.get('company_name')}': {e}")

# --------------------------------------------------
# Process one country — isolated so one failure
# does not affect others
# --------------------------------------------------

def process_country(country):
    country_name = country["country_name"]
    log.info(f"Finding companies in: {country_name}")
    prompt = get_company_prompt(country_name)

    companies = None
    max_llm_attempts = 5

    for attempt in range(max_llm_attempts):
        try:
            response = llm.invoke(prompt)
            raw = response.content.strip()

            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            companies = json.loads(raw)
            break

        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                wait = (2 ** attempt) + 1
                log.warning(
                    f"{country_name}: rate limit hit, "
                    f"waiting {wait}s (attempt {attempt + 1}/{max_llm_attempts})"
                )
                time.sleep(wait)
            else:
                log.error(f"{country_name}: LLM error on attempt {attempt + 1}: {e}")
                break

    if not companies:
        log.error(f"{country_name}: No companies returned after {max_llm_attempts} attempts, skipping.")
        return 0

    log.info(f"{country_name}: Received {len(companies)} companies")
    save_companies(country_name, companies)

    # Polite delay between countries to avoid hammering Groq
    time.sleep(2)
    return 1

# --------------------------------------------------
# Process one batch of countries
# --------------------------------------------------

def process_batch(batch):
    log.info(f"Worker started with {len(batch)} countries")
    count = 0
    for country in batch:
        try:
            count += process_country(country)
        except Exception as e:
            log.error(f"Unhandled error for country '{country.get('country_name')}': {e}")
    log.info(f"Worker finished — processed {count}/{len(batch)} countries")
    return count

# --------------------------------------------------
# Node 3 : Run Swarm
# --------------------------------------------------

def node_run_swarm(state: AgentState):
    batches = state["batches"]
    processed = 0

    # max_workers=1 kept as-is per architecture preservation;
    # raise to e.g. 3 only if you have multiple Groq API keys
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_batch, batch): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                result = future.result()
                processed += result
                log.info(f"Batch {batch_idx + 1}/{len(batches)} complete — cumulative processed: {processed}")
            except Exception as e:
                log.error(f"Batch {batch_idx + 1} raised an unexpected error: {e}")

    log.info(f"All batches done. Total countries processed: {processed}")
    return {
        **state,
        "processed": processed
    }

# --------------------------------------------------
# Build Graph
# --------------------------------------------------

graph = StateGraph(AgentState)

graph.add_node("load_countries", node_load_countries)
graph.add_node("create_batches", node_create_batches)
graph.add_node("run_swarm", node_run_swarm)

graph.set_entry_point("load_countries")

graph.add_edge("load_countries", "create_batches")
graph.add_edge("create_batches", "run_swarm")
graph.add_edge("run_swarm", END)

agent = graph.compile()

# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("=" * 60)
    print("SUB AGENT 2 - COMPANY FINDER")
    print("=" * 60)

    initial_state = {
        "countries": [],
        "batches": [],
        "processed": 0
    }

    result = agent.invoke(initial_state)

    print("\nFinished!")
    print(f"Countries Loaded : {len(result['countries'])}")
    print(f"Swarm Batches    : {len(result['batches'])}")
    print(f"Processed        : {result['processed']}")


if __name__ == "__main__":
    main()