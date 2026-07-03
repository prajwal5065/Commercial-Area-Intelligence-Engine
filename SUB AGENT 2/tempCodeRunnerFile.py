import os
import logging
from typing import TypedDict, List
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
import json
import time

from supabase_client import (
    get_countries,
    insert_company,
    company_exists,
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

    log.info(f"Created {len(batches)} swarm batches")

    return {
        **state,
        "batches": batches
    }

def get_company_prompt(country_name):

    return f"""
You are a business intelligence analyst.

Return the top 10 largest companies headquartered in {country_name}.

Return ONLY valid JSON.

Format:

[
  {{
    "company_name": "",
    "industry": "",
    "website": ""
  }}
]

No markdown.
No explanation.
No extra text.
"""
import json

def process_batch(batch):

    log.info(f"Worker started with {len(batch)} countries")

    for country in batch:

        country_name = country["country_name"]

        log.info(f"Finding companies in {country_name}")

        prompt = get_company_prompt(country_name)

        try:

            response = llm.invoke(prompt)

            companies = json.loads(response.content)

            print(f"\n===== {country_name} =====")

            print(json.dumps(companies, indent=2))

            save_companies(country_name, companies)

            time.sleep(2)

        except Exception as e:

            log.error(f"{country_name}: {e}")

    log.info("Worker finished")

    return len(batch)

def node_run_swarm(state: AgentState):

    batches = state["batches"]

    processed = 0

    with ThreadPoolExecutor(max_workers=1) as executor:

        results = executor.map(process_batch, batches)

        processed = sum(results)

    log.info(f"Processed {processed} countries")

    return {

        **state,

        "processed": processed

    }

# --------------------------------------------------
# Build Graph
# --------------------------------------------------

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
def save_companies(country_name, companies):
    for company in companies:
        try:    
            insert_company(
                company_name=company["company_name"],
                country_name=country_name,
                city_name=None,
                zone_name=None,
                category=company["industry"],
                priority=1,
                source_url=company["website"]
            )
        except Exception as e:
            log.error(f"Failed to save {company['company_name']} : {e}")
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