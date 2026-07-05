import os
import re
import json
import sys
import requests
import logging
from datetime import datetime   
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Reconfigure stdout/stderr to prevent UnicodeEncodeErrors on Windows CP1252/etc.
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass

load_dotenv()



TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_MAX_TOK = 8000
TAVILY_MAX_RES  = 7

# ── Provider registry ─────────────────────────────────────────────
# Mirrors SUB_AGENT 4 sub area mapper/main.py's PROVIDERS pattern, so the
# same manual model-choice UI/API contract works for this agent too.
PROVIDERS = {
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "api_url":     "https://api.groq.com/openai/v1/chat/completions",
        "model":       "llama-3.3-70b-versatile",
        "request_fmt": "openai",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "api_url":     "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model":       "gemini-2.0-flash",
        "request_fmt": "gemini",
    },
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "api_url":     "https://api.openai.com/v1/chat/completions",
        "model":       "gpt-4o-mini",
        "request_fmt": "openai",
    },
}

DEFAULT_PROVIDER = "groq"


def _provider_has_key(provider: str) -> bool:
    return bool(os.getenv(PROVIDERS.get(provider, {}).get("api_key_env", "")))


SYSTEM_PROMPT = """

SUB-AGENT 2 — CITY SEGMENTER
ROLE
You are the City Segmenter Agent. You receive a country name and return its cities classified into 
Tier 1, Tier 2, and Tier 3 using only official government or municipal sources for that country. 
You do not infer tier from population size or your training knowledge. Tier classification must come 
from an explicit official classification on the source page.

TOOLS: classify_city_tier, log_scrape_fail

EXECUTION STEPS
1. Receive: country_name from Orchestrator [master agent]
2. Call classify_city_tier(country) → government census portal or official municipal registry
3. For each city: city_name, tier (1/2/3), source_url, retrieved_at
4. Return ALL tiers to Orchestrator structured as:
   - tier_1_cities: [ ] 
   - tier_2_cities: [ ]
   - tier_3_cities: [ ]
   Each city record must carry: city_name, tier, country, source_url, retrieved_at.
5. FALLBACK STRATEGY: If the country has no official "Tier" system, perform "Business Importance Mapping" 
using official administrative/statistical areas (e.g., GCCSAs, SUAs, MSAs) to logically map them into 
Tiers 1, 2, and 3. If no official classification or administrative area data exists, 
return status: NO_TIER_DATA and log the country.

COMPLETENESS RULES [CRITICAL — READ BEFORE GENERATING OUTPUT]
[CRITICAL] Tier 2 lists are typically the longest. You MUST return EVERY single Tier 2 city 
           found in the official source. Do NOT summarize, truncate, abbreviate, or stop early.
[CRITICAL] Before writing your final JSON, silently count: How many Tier 2 cities did the 
           source contain? Then verify your output contains exactly that many records.
[CRITICAL] If the official source lists 50 Tier 2 cities, your tier_2_cities array must have 
           50 entries. If it lists 80, you output 80. There is no maximum cap.
[CRITICAL] Do not write "etc.", "and more", "..." or any shorthand. Every city gets its own 
           full JSON record with all required fields.
[CRITICAL] Do not group multiple cities into one record. One city = one record, always.
[CRITICAL] For Tier 3, do not use a generic placeholder. Instead, explicitly state the official definition 
	   (e.g., "All other cities not classified as Tier 1 or 2"), and then provide a list of 20-30 representative 
	   cities that fall into this category according to the source's population/classification criteria. 
	   Label these clearly as 'Sample Tier 3 Cities'.

HARD RULES
[HARD] Tier must appear explicitly in the official source OR be logically mapped 
       from official administrative areas. Never assign tier based on your own knowledge.
[HARD] Accepted sources: official government census, ministry of urban affairs, municipal 
       corporation portal. No Wikipedia, no travel sites.
[HARD] Every city record must carry source_url and retrieved_at. Records without both are 
       discarded.
[WARN] If source is down, try one alternate official source. If both fail, return SCRAPE_FAIL 
       — do not guess.

SELF-CHECK BEFORE RETURNING OUTPUT [MANDATORY]
Before finalizing your response, answer these internally:
  Q1: Did I include ALL Tier 2 cities from the source, without skipping any?
  Q2: Does each record have city_name, tier, country, source_url, and retrieved_at?
  Q3: Did I write a separate record for every city (no grouping, no "etc.")?
If any answer is NO — go back and fix before returning.

RETURN SCHEMA
{ city_name, tier, country, source_url, retrieved_at }[]
status: SUCCESS | SCRAPE_FAIL | NO_TIER_DATA

Example: 
{
  "tier_1_cities": [
    { "city_name": "Sapporo", "tier": "1", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
    { "city_name": "Sendai", "tier": "1", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
    { "city_name": "Saitama", "tier": "1", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
  ],
  "tier_2_cities": [
    { "city_name": "Akashi", "tier": "2", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
    { "city_name": "Akita", "tier": "2", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
    { "city_name": "Amagasaki", "tier": "2", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
  ],
  "tier_3_cities": [
    { "definition": "Sample Tier 3 Cities (All other cities not classified as Tier 1 or 2)", "cities": [
        { "city_name": "Otaru", "tier": "3", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
        { "city_name": "Hirosaki", "tier": "3", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
        { "city_name": "Nikko", "tier": "3", "country": "Japan", "source_url": "https://www.soumu.go.jp/english/", "retrieved_at": "2026-04-25" },
      ]
    }
  ],}

"""


def tavily_search(query: str) -> list[dict]:

    url = "https://api.tavily.com/search"
    payload = {
        "api_key":      TAVILY_API_KEY,
        "query":        query,
        "search_depth": "advanced",
        "max_results":  TAVILY_MAX_RES,
        "include_answer":      True,
        "include_raw_content": False,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results", [])
    if data.get("answer"):
        results.append({
            "title":   "Tavily synthesised answer",
            "url":     "tavily-answer",
            "content": data["answer"],
        })
    return results


def gather_search_context(country: str) -> str:
    queries = [
        f"{country} official city tier classification government census",
        f"{country} municipal registry urban agglomeration official classification",
        f"{country} ministry urban development city categories official",
    ]

    if not TAVILY_API_KEY:
        log.warning("  [Tavily] Skipping search — no API key.")
        return ""

    all_results = []
    tavily_failed = False
    for q in queries:
        log.info(f"  [Tavily] {q}")
        try:
            results = tavily_search(q)
            all_results.extend(results)
            log.info(f"           -> {len(results)} result(s)")
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["432", "429", "rate limit", "rate_limit", "too many requests", "quota", "credits"]):
                log.warning(f"           -> Tavily plan limit reached — switching to LLM-only mode.")
                tavily_failed = True
                break
            log.error(f"           -> FAILED: {e}")

    if tavily_failed:
        return ""

    log.info(f"  [Tavily] Total results collected: {len(all_results)}")

    context_parts = []
    for i, r in enumerate(all_results[:12], 1):
        content = (r.get("content") or "")[:700]
        context_parts.append(
            f"[Source {i}] {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"Content: {content}"
        )
    return "\n\n---\n\n".join(context_parts)



def groq_classify(country: str, search_context: str, provider: str = DEFAULT_PROVIDER) -> str:
    """Classify a country's cities via the chosen LLM provider. Name kept as
    groq_classify for backward compatibility with any existing callers that
    don't pass a provider - defaults to Groq, identical to prior behavior.

    provider: one of PROVIDERS' keys ("groq" | "gemini" | "openai"). Falls
    back to Groq with a warning if unknown or unconfigured, rather than
    raising - a bad choice shouldn't crash a whole country's classification.
    """
    if provider not in PROVIDERS:
        log.warning(f"  [WARN] Unknown provider '{provider}', falling back to '{DEFAULT_PROVIDER}'.")
        provider = DEFAULT_PROVIDER
    if not _provider_has_key(provider):
        log.warning(f"  [WARN] {PROVIDERS[provider]['api_key_env']} not set for provider '{provider}' — "
              f"falling back to '{DEFAULT_PROVIDER}'.")
        provider = DEFAULT_PROVIDER

    cfg = PROVIDERS[provider]
    api_key = os.getenv(cfg["api_key_env"])

    if search_context:
        user_message = (
            f"Country: {country}\n\n"
            f"Web search results from official sources:\n\n{search_context}\n\n"
            f"Task: Classify all cities of {country} into Tier 1, Tier 2, and Tier 3 "
            f"using the search results above. Apply fallback Business Importance Mapping "
            f"strategy if no explicit tier system exists. Return ONLY valid JSON."
        )
    else:
        # LLM-only fallback: no search context available
        log.info(f"  [{provider.upper()}] No Tavily context — using LLM training knowledge only.")
        user_message = (
            f"Country: {country}\n\n"
            f"Web search is currently unavailable. Use your own comprehensive training knowledge "
            f"to classify the most important cities of {country} into Tier 1, Tier 2, and Tier 3 "
            f"based on economic importance, population, and administrative significance. "
            f"For source_url, use the most relevant official government or statistical source URL you know. "
            f"Apply the Business Importance Mapping fallback strategy. "
            f"Return ONLY valid JSON — be thorough and list as many real cities as possible."
        )

    if cfg["request_fmt"] == "gemini":
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_message}"}],
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": GROQ_MAX_TOK},
        }
        headers = {"Content-Type": "application/json"}
        url = f"{cfg['api_url']}?key={api_key}"
    else:
        payload = {
            "model":       cfg["model"],
            "temperature": 0.1,
            "max_tokens":  GROQ_MAX_TOK,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        }
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        url = cfg["api_url"]

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    rj = resp.json()
    if cfg["request_fmt"] == "gemini":
        return rj["candidates"][0]["content"]["parts"][0]["text"]
    return rj["choices"][0]["message"]["content"]

 
# JSON Parsing
def repair_truncated_json(text: str) -> str:
    """
    If the JSON was cut off mid-stream, close all open arrays and objects
    so json.loads can still parse what we have.
    """
    # Remove trailing incomplete entry (last comma + anything after)
    text = re.sub(r',\s*$', '', text.rstrip())
 
    # Count unclosed brackets
    stack = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
        if not in_string:
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']') and stack:
                stack.pop()
 
    # Close all unclosed brackets in reverse order
    closing = ''.join(reversed(stack))
    return text + closing
 
 
# def parse_json(raw: str) -> dict:
#     """Strip markdown fences, repair truncation, and parse JSON."""
#     cleaned = raw.strip()
 
#     # Strip ```json ... ``` fences
#     if cleaned.startswith("```"):
#         cleaned = cleaned.split("\n", 1)[-1]
#         cleaned = cleaned.rsplit("```", 1)[0].strip()
 
#     # Extract the outermost { ... } block
#     start = cleaned.find("{")
#     end   = cleaned.rfind("}")
#     if start != -1 and end != -1:
#         cleaned = cleaned[start:end + 1]
#     elif start != -1:
#         # JSON was truncated — no closing brace found
#         cleaned = cleaned[start:]
 
#     # Try parsing as-is
#     try:
#         return json.loads(cleaned)
#     except json.JSONDecodeError:
#         pass
 
#     # Attempt to repair truncated JSON
#     print("  [Parser] JSON appears truncated — attempting repair...")
#     repaired = repair_truncated_json(cleaned)
#     try:
#         data = json.loads(repaired)
#         print("  [Parser] Repair successful.")
#         return data
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Could not parse JSON even after repair: {e}\nPreview: {cleaned[:300]}")

def parse_json(raw: str) -> dict:
    """Strip markdown fences, repair truncation, handle multiple formats, and parse JSON."""
    cleaned = raw.strip()

    # Strip ```json ... ``` fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()  # FIX: assign back to cleaned

    # ── Attempt 1: Parse as-is (handles correct nested format) ──
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # Check if it's the expected nested structure
            if any(k in data for k in ("tier_1_cities", "tier_2_cities", "tier_3_cities")):
                return data
    except json.JSONDecodeError:
        pass

    # ── Attempt 2: Extract [...] array block ──
    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")
    if arr_start != -1 and arr_end > arr_start:
        try:
            items = json.loads(cleaned[arr_start:arr_end + 1])
            if isinstance(items, list):
                print("  [Parser] LLM returned flat array — normalizing to tier structure...")
                return _group_flat_cities(items)
        except json.JSONDecodeError:
            pass

    # ── Attempt 3: Extract { ... } block ──
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        block = cleaned[start:end + 1]
        
        # Try parsing the object directly
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                if any(k in data for k in ("tier_1_cities", "tier_2_cities", "tier_3_cities")):
                    return data
        except json.JSONDecodeError:
            pass

        # Check if it's multiple objects without brackets: { ... }, { ... }
        if re.search(r'\}\s*,\s*\{', block):
            print("  [Parser] Found multiple objects without array wrapper — wrapping and normalizing...")
            wrapped = "[" + block + "]"
            try:
                items = json.loads(wrapped)
                if isinstance(items, list):
                    return _group_flat_cities(items)
            except json.JSONDecodeError:
                pass

        # Attempt truncation repair on this block
        print("  [Parser] JSON appears truncated — attempting repair...")
        repaired = repair_truncated_json(block)
        try:
            data = json.loads(repaired)
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                return _group_flat_cities(data)
            print("  [Parser] Repair successful but unexpected format.")
            return data
        except json.JSONDecodeError:
            pass

    # ── Attempt 4: No closing } found — extract from first { to end ──
    elif start != -1:
        block = cleaned[start:]
        print("  [Parser] No closing brace found — attempting repair...")
        repaired = repair_truncated_json(block)
        try:
            data = json.loads(repaired)
            return data
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON. Preview: {cleaned[:300]}")


def _group_flat_cities(items: list) -> dict:
    """
    Convert a flat list of city objects into the nested tier structure.
    
    Input:  [{"city_name": "Delhi", "tier": "1"}, {"city_name": "Pune", "tier": "2"}, ...]
    Output: {"tier_1_cities": [...], "tier_2_cities": [...], "tier_3_cities": [...]}
    """
    tier_1 = []
    tier_2 = []
    tier_3 = []
    
    for item in items:
        if not isinstance(item, dict) or not item.get("city_name"):
            continue
        
        tier = str(item.get("tier", item.get("tier_level", ""))).strip().lower()
        city_entry = {
            "city_name": item.get("city_name", ""),
            "tier": str(item.get("tier", "")).strip(),
            "country": item.get("country", ""),
            "source_url": item.get("source_url", ""),
            "retrieved_at": item.get("retrieved_at", ""),
        }
        
        if tier in ("1", "tier_1", "tier 1", "t1", "i"):
            tier_1.append(city_entry)
        elif tier in ("2", "tier_2", "tier 2", "t2", "ii"):
            tier_2.append(city_entry)
        else:
            tier_3.append({"cities": [city_entry]})
    
    result = {
        "tier_1_cities": tier_1,
        "tier_2_cities": tier_2,
        "tier_3_cities": tier_3,
    }
    
    print(f"  [Parser] Normalized: {len(tier_1)} T1, {len(tier_2)} T2, {len(tier_3)} T3 groups")
    return result


def print_results(data: dict) -> None:
    t1 = data.get("tier_1_cities", [])
    t2 = data.get("tier_2_cities", [])
    t3 = data.get("tier_3_cities", [])

    divider = "=" * 65

    # print(f"\n{divider}")
    # print(f"  CITY TIER CLASSIFICATION — {data.get('country', '').upper()}")
    # print(divider)
    # print(f"  Status  : {data.get('status', 'UNKNOWN')}")
    # print(f"  Source  : {data.get('tier_definition_source', 'N/A')}")
    # print(f"  Log     : {data.get('log', '')}")
    # print(f"  Tier 1  : {len(t1)} cities")
    # print(f"  Tier 2  : {len(t2)} cities")
    # print(f"  Tier 3  : {len(t3)} cities (sample)")
    # print(divider)

    print(json.dumps(data, indent=2, ensure_ascii=False))



# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────
def process_country(country: str, provider: str = DEFAULT_PROVIDER) -> dict:
    """
    Reusable worker function for Master Agent.
    Takes a country name and returns parsed JSON data.

    provider: which LLM to use for classification ("groq" | "gemini" |
    "openai"). Manual choice, forwarded to groq_classify(). Defaults to
    "groq", matching behavior before provider choice existed.
    """

    if not country:
        raise ValueError("Country name cannot be empty")

    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    if not _provider_has_key(provider):
        # groq_classify() will itself fall back further and warn; only raise
        # here if there's truly no usable key anywhere in the chain.
        if not any(_provider_has_key(p) for p in PROVIDERS):
            raise ValueError(
                "No LLM provider API key found (checked GROQ_API_KEY, "
                "GEMINI_API_KEY, OPENAI_API_KEY)."
            )

    if not TAVILY_API_KEY:
        log.warning("  [Tavily] No API key — running in LLM-only mode.")

    log.info(f"[Agent] Country : {country}")
    log.info(f"[Agent] LLM     : {PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])['model']} via {provider}")

    if TAVILY_API_KEY:
        log.info("[Step 1/3] Searching official sources via Tavily...")
    else:
        log.info("[Step 1/3] Tavily unavailable — skipping search, using LLM-only mode...")
    search_context = gather_search_context(country)

    if search_context:
        log.info(f"[Step 2/3] Classifying cities via {provider} (with search context)...")
    else:
        log.info(f"[Step 2/3] Classifying cities via {provider} (LLM-only, no search context)...")
    raw_response = groq_classify(country, search_context, provider=provider)

    log.info(f"  [{provider.upper()}] Response received ({len(raw_response)} chars)")

    log.info("[Step 3/3] Parsing JSON...")
    data = parse_json(raw_response)

    return data



def main():

    if len(sys.argv) > 1:
        country = " ".join(sys.argv[1:]).strip()
    else:
        country = input("Enter country name: ").strip()

    try:
        data = process_country(country)

        print("\n===== RESULT =====\n")
        print_results(data)

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
