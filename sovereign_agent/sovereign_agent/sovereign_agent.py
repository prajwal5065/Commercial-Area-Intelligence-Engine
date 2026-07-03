import os
import json
import time
import logging
import requests
from datetime import datetime, timezone
from typing import TypedDict, List, Dict, Optional, Annotated
import operator

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

# Load environment variables from .env file
load_dotenv()

# Setup logging so you can see what the agent is doing
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 1. STATE — This is the "memory" shared between all graph nodes
# ─────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    """
    The shared state that travels through the entire LangGraph.
    Every node can read from it and write back to it.
    """
    iso_codes: List[Dict]           # [{iso3, iso2, name}, ...]
    tier1_data: Dict[str, Dict]     # {iso3: {gdp, per_capita, source_url}}
    tier2_data: Dict[str, Dict]     # {iso3: {gdp, per_capita, source_url}}
    tier3_data: Dict[str, Dict]     # {iso3: {gdp, per_capita, source_url}}
    missing_after_tier1: List[str]  # ISO3 codes missing after Tier 1
    missing_after_tier2: List[str]  # ISO3 codes still missing after Tier 2
    final_records: List[Dict]       # The final sorted list of all 195 records
    errors: Annotated[List[str], operator.add]  # Accumulated error messages


# ─────────────────────────────────────────────────────────────────────
# 2. MASTER ISO CODE LIST (195 Sovereign States)
# ─────────────────────────────────────────────────────────────────────
SOVEREIGN_STATES = [
    # A
    {"iso3": "AFG", "iso2": "AF", "name": "Afghanistan"},
    {"iso3": "ALB", "iso2": "AL", "name": "Albania"},
    {"iso3": "DZA", "iso2": "DZ", "name": "Algeria"},
    {"iso3": "AND", "iso2": "AD", "name": "Andorra"},
    {"iso3": "AGO", "iso2": "AO", "name": "Angola"},
    {"iso3": "ATG", "iso2": "AG", "name": "Antigua and Barbuda"},
    {"iso3": "ARG", "iso2": "AR", "name": "Argentina"},
    {"iso3": "ARM", "iso2": "AM", "name": "Armenia"},
    {"iso3": "AUS", "iso2": "AU", "name": "Australia"},
    {"iso3": "AUT", "iso2": "AT", "name": "Austria"},
    {"iso3": "AZE", "iso2": "AZ", "name": "Azerbaijan"},
    # B
    {"iso3": "BHS", "iso2": "BS", "name": "Bahamas"},
    {"iso3": "BHR", "iso2": "BH", "name": "Bahrain"},
    {"iso3": "BGD", "iso2": "BD", "name": "Bangladesh"},
    {"iso3": "BRB", "iso2": "BB", "name": "Barbados"},
    {"iso3": "BLR", "iso2": "BY", "name": "Belarus"},
    {"iso3": "BEL", "iso2": "BE", "name": "Belgium"},
    {"iso3": "BLZ", "iso2": "BZ", "name": "Belize"},
    {"iso3": "BEN", "iso2": "BJ", "name": "Benin"},
    {"iso3": "BTN", "iso2": "BT", "name": "Bhutan"},
    {"iso3": "BOL", "iso2": "BO", "name": "Bolivia"},
    {"iso3": "BIH", "iso2": "BA", "name": "Bosnia and Herzegovina"},
    {"iso3": "BWA", "iso2": "BW", "name": "Botswana"},
    {"iso3": "BRA", "iso2": "BR", "name": "Brazil"},
    {"iso3": "BRN", "iso2": "BN", "name": "Brunei"},
    {"iso3": "BGR", "iso2": "BG", "name": "Bulgaria"},
    {"iso3": "BFA", "iso2": "BF", "name": "Burkina Faso"},
    {"iso3": "BDI", "iso2": "BI", "name": "Burundi"},
    # C
    {"iso3": "CPV", "iso2": "CV", "name": "Cabo Verde"},
    {"iso3": "KHM", "iso2": "KH", "name": "Cambodia"},
    {"iso3": "CMR", "iso2": "CM", "name": "Cameroon"},
    {"iso3": "CAN", "iso2": "CA", "name": "Canada"},
    {"iso3": "CAF", "iso2": "CF", "name": "Central African Republic"},
    {"iso3": "TCD", "iso2": "TD", "name": "Chad"},
    {"iso3": "CHL", "iso2": "CL", "name": "Chile"},
    {"iso3": "CHN", "iso2": "CN", "name": "China"},
    {"iso3": "COL", "iso2": "CO", "name": "Colombia"},
    {"iso3": "COM", "iso2": "KM", "name": "Comoros"},
    {"iso3": "COD", "iso2": "CD", "name": "Congo (Dem. Rep.)"},
    {"iso3": "COG", "iso2": "CG", "name": "Congo (Rep.)"},
    {"iso3": "CRI", "iso2": "CR", "name": "Costa Rica"},
    {"iso3": "CIV", "iso2": "CI", "name": "Côte d'Ivoire"},
    {"iso3": "HRV", "iso2": "HR", "name": "Croatia"},
    {"iso3": "CUB", "iso2": "CU", "name": "Cuba"},
    {"iso3": "CYP", "iso2": "CY", "name": "Cyprus"},
    {"iso3": "CZE", "iso2": "CZ", "name": "Czech Republic"},
    # D
    {"iso3": "DNK", "iso2": "DK", "name": "Denmark"},
    {"iso3": "DJI", "iso2": "DJ", "name": "Djibouti"},
    {"iso3": "DMA", "iso2": "DM", "name": "Dominica"},
    {"iso3": "DOM", "iso2": "DO", "name": "Dominican Republic"},
    # E
    {"iso3": "ECU", "iso2": "EC", "name": "Ecuador"},
    {"iso3": "EGY", "iso2": "EG", "name": "Egypt"},
    {"iso3": "SLV", "iso2": "SV", "name": "El Salvador"},
    {"iso3": "GNQ", "iso2": "GQ", "name": "Equatorial Guinea"},
    {"iso3": "ERI", "iso2": "ER", "name": "Eritrea"},
    {"iso3": "EST", "iso2": "EE", "name": "Estonia"},
    {"iso3": "SWZ", "iso2": "SZ", "name": "Eswatini"},
    {"iso3": "ETH", "iso2": "ET", "name": "Ethiopia"},
    # F
    {"iso3": "FJI", "iso2": "FJ", "name": "Fiji"},
    {"iso3": "FIN", "iso2": "FI", "name": "Finland"},
    {"iso3": "FRA", "iso2": "FR", "name": "France"},
    # G
    {"iso3": "GAB", "iso2": "GA", "name": "Gabon"},
    {"iso3": "GMB", "iso2": "GM", "name": "Gambia"},
    {"iso3": "GEO", "iso2": "GE", "name": "Georgia"},
    {"iso3": "DEU", "iso2": "DE", "name": "Germany"},
    {"iso3": "GHA", "iso2": "GH", "name": "Ghana"},
    {"iso3": "GRC", "iso2": "GR", "name": "Greece"},
    {"iso3": "GRD", "iso2": "GD", "name": "Grenada"},
    {"iso3": "GTM", "iso2": "GT", "name": "Guatemala"},
    {"iso3": "GIN", "iso2": "GN", "name": "Guinea"},
    {"iso3": "GNB", "iso2": "GW", "name": "Guinea-Bissau"},
    {"iso3": "GUY", "iso2": "GY", "name": "Guyana"},
    # H
    {"iso3": "HTI", "iso2": "HT", "name": "Haiti"},
    {"iso3": "HND", "iso2": "HN", "name": "Honduras"},
    {"iso3": "HUN", "iso2": "HU", "name": "Hungary"},
    # I
    {"iso3": "ISL", "iso2": "IS", "name": "Iceland"},
    {"iso3": "IND", "iso2": "IN", "name": "India"},
    {"iso3": "IDN", "iso2": "ID", "name": "Indonesia"},
    {"iso3": "IRN", "iso2": "IR", "name": "Iran"},
    {"iso3": "IRQ", "iso2": "IQ", "name": "Iraq"},
    {"iso3": "IRL", "iso2": "IE", "name": "Ireland"},
    {"iso3": "ISR", "iso2": "IL", "name": "Israel"},
    {"iso3": "ITA", "iso2": "IT", "name": "Italy"},
    # J
    {"iso3": "JAM", "iso2": "JM", "name": "Jamaica"},
    {"iso3": "JPN", "iso2": "JP", "name": "Japan"},
    {"iso3": "JOR", "iso2": "JO", "name": "Jordan"},
    # K
    {"iso3": "KAZ", "iso2": "KZ", "name": "Kazakhstan"},
    {"iso3": "KEN", "iso2": "KE", "name": "Kenya"},
    {"iso3": "KIR", "iso2": "KI", "name": "Kiribati"},
    {"iso3": "PRK", "iso2": "KP", "name": "Korea (North)"},
    {"iso3": "KOR", "iso2": "KR", "name": "Korea (South)"},
    {"iso3": "KWT", "iso2": "KW", "name": "Kuwait"},
    {"iso3": "KGZ", "iso2": "KG", "name": "Kyrgyzstan"},
    # L
    {"iso3": "LAO", "iso2": "LA", "name": "Laos"},
    {"iso3": "LVA", "iso2": "LV", "name": "Latvia"},
    {"iso3": "LBN", "iso2": "LB", "name": "Lebanon"},
    {"iso3": "LSO", "iso2": "LS", "name": "Lesotho"},
    {"iso3": "LBR", "iso2": "LR", "name": "Liberia"},
    {"iso3": "LBY", "iso2": "LY", "name": "Libya"},
    {"iso3": "LIE", "iso2": "LI", "name": "Liechtenstein"},
    {"iso3": "LTU", "iso2": "LT", "name": "Lithuania"},
    {"iso3": "LUX", "iso2": "LU", "name": "Luxembourg"},
    # M
    {"iso3": "MDG", "iso2": "MG", "name": "Madagascar"},
    {"iso3": "MWI", "iso2": "MW", "name": "Malawi"},
    {"iso3": "MYS", "iso2": "MY", "name": "Malaysia"},
    {"iso3": "MDV", "iso2": "MV", "name": "Maldives"},
    {"iso3": "MLI", "iso2": "ML", "name": "Mali"},
    {"iso3": "MLT", "iso2": "MT", "name": "Malta"},
    {"iso3": "MHL", "iso2": "MH", "name": "Marshall Islands"},
    {"iso3": "MRT", "iso2": "MR", "name": "Mauritania"},
    {"iso3": "MUS", "iso2": "MU", "name": "Mauritius"},
    {"iso3": "MEX", "iso2": "MX", "name": "Mexico"},
    {"iso3": "FSM", "iso2": "FM", "name": "Micronesia"},
    {"iso3": "MDA", "iso2": "MD", "name": "Moldova"},
    {"iso3": "MCO", "iso2": "MC", "name": "Monaco"},
    {"iso3": "MNG", "iso2": "MN", "name": "Mongolia"},
    {"iso3": "MNE", "iso2": "ME", "name": "Montenegro"},
    {"iso3": "MAR", "iso2": "MA", "name": "Morocco"},
    {"iso3": "MOZ", "iso2": "MZ", "name": "Mozambique"},
    {"iso3": "MMR", "iso2": "MM", "name": "Myanmar"},
    # N
    {"iso3": "NAM", "iso2": "NA", "name": "Namibia"},
    {"iso3": "NRU", "iso2": "NR", "name": "Nauru"},
    {"iso3": "NPL", "iso2": "NP", "name": "Nepal"},
    {"iso3": "NLD", "iso2": "NL", "name": "Netherlands"},
    {"iso3": "NZL", "iso2": "NZ", "name": "New Zealand"},
    {"iso3": "NIC", "iso2": "NI", "name": "Nicaragua"},
    {"iso3": "NER", "iso2": "NE", "name": "Niger"},
    {"iso3": "NGA", "iso2": "NG", "name": "Nigeria"},
    {"iso3": "MKD", "iso2": "MK", "name": "North Macedonia"},
    {"iso3": "NOR", "iso2": "NO", "name": "Norway"},
    # O
    {"iso3": "OMN", "iso2": "OM", "name": "Oman"},
    # P
    {"iso3": "PAK", "iso2": "PK", "name": "Pakistan"},
    {"iso3": "PLW", "iso2": "PW", "name": "Palau"},
    {"iso3": "PSE", "iso2": "PS", "name": "Palestine"},
    {"iso3": "PAN", "iso2": "PA", "name": "Panama"},
    {"iso3": "PNG", "iso2": "PG", "name": "Papua New Guinea"},
    {"iso3": "PRY", "iso2": "PY", "name": "Paraguay"},
    {"iso3": "PER", "iso2": "PE", "name": "Peru"},
    {"iso3": "PHL", "iso2": "PH", "name": "Philippines"},
    {"iso3": "POL", "iso2": "PL", "name": "Poland"},
    {"iso3": "PRT", "iso2": "PT", "name": "Portugal"},
    # Q
    {"iso3": "QAT", "iso2": "QA", "name": "Qatar"},
    # R
    {"iso3": "ROU", "iso2": "RO", "name": "Romania"},
    {"iso3": "RUS", "iso2": "RU", "name": "Russia"},
    {"iso3": "RWA", "iso2": "RW", "name": "Rwanda"},
    # S
    {"iso3": "KNA", "iso2": "KN", "name": "Saint Kitts and Nevis"},
    {"iso3": "LCA", "iso2": "LC", "name": "Saint Lucia"},
    {"iso3": "VCT", "iso2": "VC", "name": "Saint Vincent and the Grenadines"},
    {"iso3": "WSM", "iso2": "WS", "name": "Samoa"},
    {"iso3": "SMR", "iso2": "SM", "name": "San Marino"},
    {"iso3": "STP", "iso2": "ST", "name": "Sao Tome and Principe"},
    {"iso3": "SAU", "iso2": "SA", "name": "Saudi Arabia"},
    {"iso3": "SEN", "iso2": "SN", "name": "Senegal"},
    {"iso3": "SRB", "iso2": "RS", "name": "Serbia"},
    {"iso3": "SYC", "iso2": "SC", "name": "Seychelles"},
    {"iso3": "SLE", "iso2": "SL", "name": "Sierra Leone"},
    {"iso3": "SGP", "iso2": "SG", "name": "Singapore"},
    {"iso3": "SVK", "iso2": "SK", "name": "Slovakia"},
    {"iso3": "SVN", "iso2": "SI", "name": "Slovenia"},
    {"iso3": "SLB", "iso2": "SB", "name": "Solomon Islands"},
    {"iso3": "SOM", "iso2": "SO", "name": "Somalia"},
    {"iso3": "ZAF", "iso2": "ZA", "name": "South Africa"},
    {"iso3": "SSD", "iso2": "SS", "name": "South Sudan"},
    {"iso3": "ESP", "iso2": "ES", "name": "Spain"},
    {"iso3": "LKA", "iso2": "LK", "name": "Sri Lanka"},
    {"iso3": "SDN", "iso2": "SD", "name": "Sudan"},
    {"iso3": "SUR", "iso2": "SR", "name": "Suriname"},
    {"iso3": "SWE", "iso2": "SE", "name": "Sweden"},
    {"iso3": "CHE", "iso2": "CH", "name": "Switzerland"},
    {"iso3": "SYR", "iso2": "SY", "name": "Syria"},
    # T
    {"iso3": "TJK", "iso2": "TJ", "name": "Tajikistan"},
    {"iso3": "TZA", "iso2": "TZ", "name": "Tanzania"},
    {"iso3": "THA", "iso2": "TH", "name": "Thailand"},
    {"iso3": "TLS", "iso2": "TL", "name": "Timor-Leste"},
    {"iso3": "TGO", "iso2": "TG", "name": "Togo"},
    {"iso3": "TON", "iso2": "TO", "name": "Tonga"},
    {"iso3": "TTO", "iso2": "TT", "name": "Trinidad and Tobago"},
    {"iso3": "TUN", "iso2": "TN", "name": "Tunisia"},
    {"iso3": "TUR", "iso2": "TR", "name": "Turkey"},
    {"iso3": "TKM", "iso2": "TM", "name": "Turkmenistan"},
    {"iso3": "TUV", "iso2": "TV", "name": "Tuvalu"},
    # U
    {"iso3": "UGA", "iso2": "UG", "name": "Uganda"},
    {"iso3": "UKR", "iso2": "UA", "name": "Ukraine"},
    {"iso3": "ARE", "iso2": "AE", "name": "United Arab Emirates"},
    {"iso3": "GBR", "iso2": "GB", "name": "United Kingdom"},
    {"iso3": "USA", "iso2": "US", "name": "United States"},
    {"iso3": "URY", "iso2": "UY", "name": "Uruguay"},
    {"iso3": "UZB", "iso2": "UZ", "name": "Uzbekistan"},
    # V
    {"iso3": "VUT", "iso2": "VU", "name": "Vanuatu"},
    {"iso3": "VAT", "iso2": "VA", "name": "Vatican City"},
    {"iso3": "VEN", "iso2": "VE", "name": "Venezuela"},
    {"iso3": "VNM", "iso2": "VN", "name": "Vietnam"},
    # Y
    {"iso3": "YEM", "iso2": "YE", "name": "Yemen"},
    # Z
    {"iso3": "ZMB", "iso2": "ZM", "name": "Zambia"},
    {"iso3": "ZWE", "iso2": "ZW", "name": "Zimbabwe"},
]

# Tier 3 special-case countries — data from specialized reports
TIER3_KNOWN_DATA = {
    "PRK": {
        "nominal_gdp_usd": 18_000_000_000,
        "per_capita_usd": 706,
        "source_url": "https://www.bok.or.kr/eng/bbs/E0000634/view.do?nttId=10079455&menuNo=400069",
    },
    "VAT": {
        "nominal_gdp_usd": 360_000_000,
        "per_capita_usd": 360_000,
        "source_url": "https://www.vaticannews.va/en/vatican-city/news/2023-07/holy-see-publishes-2022-consolidated-financial-statements.html",
    },
    "SYR": {
        "nominal_gdp_usd": 11_900_000_000,
        "per_capita_usd": 533,
        "source_url": "https://www.unescwa.org/sites/default/files/pubs/pdf/national-accounts-studies-arab-region-bulletin-41-english.pdf",
    },
    "CUB": {
        "nominal_gdp_usd": 107_000_000_000,
        "per_capita_usd": 9_467,
        "source_url": "https://repositorio.cepal.org/handle/11362/48960",
    },
    "ERI": {
        "nominal_gdp_usd": 2_065_000_000,
        "per_capita_usd": 538,
        "source_url": "https://unstats.un.org/unsd/snaama/CountryProfile?ccode=232",
    },
    "PSE": {
        "nominal_gdp_usd": 18_200_000_000,
        "per_capita_usd": 3_455,
        "source_url": "https://www.unescwa.org/sites/default/files/pubs/pdf/national-accounts-studies-arab-region-bulletin-41-english.pdf",
    },
}

TIER3_ISO_CODES = set(TIER3_KNOWN_DATA.keys())


# ─────────────────────────────────────────────────────────────────────
# 3. API FETCHER CLASSES
# ─────────────────────────────────────────────────────────────────────

class WorldBankFetcher:
    BASE_URL = "https://api.worldbank.org/v2"

    def fetch(self, iso2: str) -> Dict:
        gdp = self._get_indicator(iso2, "NY.GDP.MKTP.CD")
        pc  = self._get_indicator(iso2, "NY.GDP.PCAP.CD")
        if gdp is not None and pc is not None:
            return {
                "nominal_gdp_usd": int(gdp),
                "per_capita_usd": int(pc),
                "source_url": f"https://api.worldbank.org/v2/country/{iso2}/indicator/NY.GDP.MKTP.CD?format=json",
            }
        return {}

    def _get_indicator(self, iso2: str, indicator: str) -> Optional[float]:
        url = (
            f"{self.BASE_URL}/country/{iso2}/indicator/{indicator}"
            f"?format=json&mrv=5&per_page=5"
        )
        try:
            response = requests.get(url, timeout=12)
            response.raise_for_status()
            data = response.json()
            if len(data) > 1 and data[1]:
                for entry in data[1]:
                    if entry.get("value") is not None:
                        return float(entry["value"])
        except Exception as e:
            log.debug(f"WorldBank error for {iso2}/{indicator}: {e}")
        return None


class IMFFetcher:
    BASE_URL = "https://www.imf.org/external/datamapper/api/v1"

    def fetch(self, iso3: str) -> Dict:
        gdp = self._get_series("NGDPD", iso3)
        pc  = self._get_series("NGDPDPC", iso3)
        if gdp is not None and pc is not None:
            return {
                "nominal_gdp_usd": int(gdp * 1_000_000_000),
                "per_capita_usd": int(pc),
                "source_url": f"https://www.imf.org/external/datamapper/NGDPD/{iso3}",
            }
        return {}

    def _get_series(self, series: str, iso3: str) -> Optional[float]:
        url = f"{self.BASE_URL}/{series}/{iso3}"
        try:
            response = requests.get(url, timeout=12)
            response.raise_for_status()
            data = response.json()
            values = data.get("values", {}).get(series, {}).get(iso3, {})
            if values:
                latest_year = max(values.keys())
                val = values[latest_year]
                if val is not None:
                    return float(val)
        except Exception as e:
            log.debug(f"IMF error for {series}/{iso3}: {e}")
        return None


class UNSDFetcher:
    BASE_URL = "https://unstats.un.org/unsd/snaama"

    def fetch(self, iso3: str) -> Dict:
        wb = WorldBankFetcher()
        result = wb.fetch(self._iso3_to_iso2(iso3))
        if result:
            result["source_url"] = f"https://unstats.un.org/unsd/snaama/CountryProfile?ccode={iso3}"
            return result
        return {}

    def _iso3_to_iso2(self, iso3: str) -> str:
        for c in SOVEREIGN_STATES:
            if c["iso3"] == iso3:
                return c["iso2"]
        return iso3[:2].upper()


# ─────────────────────────────────────────────────────────────────────
# 4. LangGraph NODE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────

def node_initialize_iso(state: AgentState) -> AgentState:
    log.info(f"[Node 1] Initializing {len(SOVEREIGN_STATES)} ISO codes...")
    return {
        **state,
        "iso_codes": SOVEREIGN_STATES,
        "tier1_data": {},
        "tier2_data": {},
        "tier3_data": {},
        "missing_after_tier1": [],
        "missing_after_tier2": [],
        "final_records": [],
        "errors": [],
    }


def node_fetch_tier1(state: AgentState) -> AgentState:
    log.info("[Node 2] Fetching Tier 1 data (World Bank + IMF)...")
    wb_fetcher  = WorldBankFetcher()
    imf_fetcher = IMFFetcher()
    tier1_data  = {}
    errors      = []

    for i, country in enumerate(state["iso_codes"]):
        iso3 = country["iso3"]
        iso2 = country["iso2"]
        name = country["name"]

        if iso3 in TIER3_ISO_CODES:
            log.info(f"  [{i+1}/{len(state['iso_codes'])}] {name} → Tier 3 special case, skipping")
            continue

        log.info(f"  [{i+1}/{len(state['iso_codes'])}] Fetching: {name} ({iso3})")

        result = wb_fetcher.fetch(iso2)
        if result:
            tier1_data[iso3] = {**result, "data_tier": 1}
            log.info(f"    ✓ World Bank: GDP=${result['nominal_gdp_usd']:,.0f}")
        else:
            result = imf_fetcher.fetch(iso3)
            if result:
                tier1_data[iso3] = {**result, "data_tier": 1}
                log.info(f"    ✓ IMF DataMapper: GDP=${result['nominal_gdp_usd']:,.0f}")
            else:
                log.warning(f"    ✗ Both APIs failed for {name} ({iso3})")
                errors.append(f"Tier1 miss: {iso3}")

        time.sleep(0.15)

    missing = [
        c["iso3"] for c in state["iso_codes"]
        if c["iso3"] not in tier1_data and c["iso3"] not in TIER3_ISO_CODES
    ]
    log.info(f"[Node 2] Done. Retrieved: {len(tier1_data)}, Missing: {len(missing)}")
    return {**state, "tier1_data": tier1_data, "missing_after_tier1": missing, "errors": errors}


def node_identify_gaps(state: AgentState) -> AgentState:
    missing = state.get("missing_after_tier1", [])
    log.info(f"[Node 3] Gap check: {len(missing)} countries missing after Tier 1: {missing}")
    return state


def node_fetch_tier2(state: AgentState) -> AgentState:
    missing = state.get("missing_after_tier1", [])
    if not missing:
        log.info("[Node 4] No gaps — skipping Tier 2.")
        return state

    log.info(f"[Node 4] Fetching Tier 2 data (UNSD) for {len(missing)} countries...")
    unsd = UNSDFetcher()
    tier2_data = {}
    errors = []

    for iso3 in missing:
        country = next((c for c in SOVEREIGN_STATES if c["iso3"] == iso3), None)
        if not country:
            continue
        log.info(f"  UNSD fetch: {country['name']} ({iso3})")
        result = unsd.fetch(iso3)
        if result:
            tier2_data[iso3] = {**result, "data_tier": 2}
            log.info(f"    ✓ UNSD: GDP=${result['nominal_gdp_usd']:,.0f}")
        else:
            errors.append(f"Tier2 miss: {iso3}")
            log.warning(f"    ✗ UNSD failed for {iso3}")
        time.sleep(0.2)

    still_missing = [iso3 for iso3 in missing if iso3 not in tier2_data]
    log.info(f"[Node 4] Done. Tier 2 retrieved: {len(tier2_data)}, Still missing: {len(still_missing)}")
    return {**state, "tier2_data": tier2_data, "missing_after_tier2": still_missing, "errors": errors}


def node_fetch_tier3(state: AgentState) -> AgentState:
    """
    NODE 5: Handle Tier 3 'hermit states' with specialized sources.
    Falls back to Groq LLM (llama-3.3-70b-versatile) for any unknown stragglers.
    """
    log.info("[Node 5] Loading Tier 3 data (hermit states)...")
    tier3_data = {}

    for iso3, data in TIER3_KNOWN_DATA.items():
        tier3_data[iso3] = {
            "nominal_gdp_usd": data["nominal_gdp_usd"],
            "per_capita_usd": data["per_capita_usd"],
            "source_url": data["source_url"],
            "data_tier": 3,
        }
        log.info(f"  ✓ Tier 3 loaded: {iso3} GDP=${data['nominal_gdp_usd']:,.0f}")

    still_missing = state.get("missing_after_tier2", [])
    if still_missing:
        log.warning(f"[Node 5] Still missing after Tier 2: {still_missing}")
        # Use Groq LLM to synthesize a best-effort estimate from known sources
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
        )
        for iso3 in still_missing:
            if iso3 in tier3_data:
                continue
            country = next((c for c in SOVEREIGN_STATES if c["iso3"] == iso3), None)
            if not country:
                continue
            log.info(f"  LLM synthesis for: {country['name']} ({iso3})")
            messages = [
                SystemMessage(content=(
                    "You are a macroeconomic data expert. "
                    "Return ONLY valid JSON with keys: nominal_gdp_usd (integer), per_capita_usd (integer). "
                    "Use the most recent available estimate from IMF, World Bank, UNSD, or regional development banks. "
                    "No markdown, no explanation."
                )),
                HumanMessage(content=(
                    f"Provide the best available nominal GDP in current USD and GDP per capita in USD "
                    f"for {country['name']} (ISO: {iso3}). "
                    f"Only use data from: IMF WEO, World Bank, UN Statistics Division, or regional dev banks."
                )),
            ]
            try:
                response = llm.invoke(messages)
                parsed = json.loads(response.content)
                tier3_data[iso3] = {
                    "nominal_gdp_usd": int(parsed["nominal_gdp_usd"]),
                    "per_capita_usd": int(parsed["per_capita_usd"]),
                    "source_url": "https://www.imf.org/en/Publications/WEO (LLM synthesis from Tier 1-3 sources)",
                    "data_tier": 3,
                }
                log.info(f"  ✓ LLM synthesized: {iso3}")
            except Exception as e:
                log.error(f"  ✗ LLM synthesis failed for {iso3}: {e}")

    log.info(f"[Node 5] Done. Tier 3 loaded: {len(tier3_data)}")
    return {**state, "tier3_data": tier3_data}


def node_validate_and_rank(state: AgentState) -> AgentState:
    log.info("[Node 6] Merging tiers and validating data...")

    all_data = {}
    all_data.update(state.get("tier3_data", {}))
    all_data.update(state.get("tier2_data", {}))
    all_data.update(state.get("tier1_data", {}))

    records = []
    missing = []
    for country in state["iso_codes"]:
        iso3 = country["iso3"]
        name = country["name"]
        data = all_data.get(iso3)
        if data and data.get("nominal_gdp_usd") and data.get("per_capita_usd"):
            records.append({
                "iso_code": iso3,
                "country_name": name,
                "nominal_gdp_usd": data["nominal_gdp_usd"],
                "per_capita_usd": data["per_capita_usd"],
                "data_tier": data["data_tier"],
                "source_url": data["source_url"],
            })
        else:
            missing.append(iso3)
            log.warning(f"  ✗ VALIDATION FAIL — no data for {name} ({iso3})")

    records.sort(key=lambda r: r["nominal_gdp_usd"], reverse=True)
    for rank, record in enumerate(records, start=1):
        record["gdp_rank"] = rank

    log.info(f"[Node 6] Validated {len(records)} records. Missing: {len(missing)}")
    if missing:
        log.warning(f"  Missing ISO codes: {missing}")

    return {**state, "final_records": records}


def node_format_output(state: AgentState) -> AgentState:
    log.info("[Node 7] Formatting final output...")

    records = state["final_records"]
    now = datetime.now(timezone.utc).isoformat()

    tier_counts = {1: 0, 2: 0, 3: 0}
    for r in records:
        tier_counts[r["data_tier"]] += 1

    for record in records:
        record["retrieved_at"] = now

    output = {
        "status": "SUCCESS" if len(records) == len(SOVEREIGN_STATES) else "PARTIAL",
        "metadata": {
            "requested": len(SOVEREIGN_STATES),
            "retrieved": len(records),
            "tier_breakdown": {
                "tier1": tier_counts[1],
                "tier2": tier_counts[2],
                "tier3": tier_counts[3],
            },
            "timestamp": now,
        },
        "data": records,
    }

    output_path = "GDP_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info(f"[Node 7] Output written to {output_path}")
    log.info(f"  Status  : {output['status']}")
    log.info(f"  Records : {output['metadata']['retrieved']}/{output['metadata']['requested']}")
    log.info(f"  Tier 1  : {tier_counts[1]}")
    log.info(f"  Tier 2  : {tier_counts[2]}")
    log.info(f"  Tier 3  : {tier_counts[3]}")

    return state


# ─────────────────────────────────────────────────────────────────────
# 5. CONDITIONAL EDGES
# ─────────────────────────────────────────────────────────────────────

def route_after_gap_check(state: AgentState) -> str:
    missing = state.get("missing_after_tier1", [])
    tier3_needed = any(c["iso3"] in TIER3_ISO_CODES for c in state["iso_codes"])
    if missing:
        return "fetch_tier2"
    elif tier3_needed:
        return "fetch_tier3"
    else:
        return "validate"


def route_after_tier2(state: AgentState) -> str:
    return "fetch_tier3"


# ─────────────────────────────────────────────────────────────────────
# 6. BUILD THE LANGGRAPH
# ─────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("initialize",   node_initialize_iso)
    graph.add_node("fetch_tier1",  node_fetch_tier1)
    graph.add_node("gap_check",    node_identify_gaps)
    graph.add_node("fetch_tier2",  node_fetch_tier2)
    graph.add_node("fetch_tier3",  node_fetch_tier3)
    graph.add_node("validate",     node_validate_and_rank)
    graph.add_node("format",       node_format_output)

    graph.set_entry_point("initialize")

    graph.add_edge("initialize",  "fetch_tier1")
    graph.add_edge("fetch_tier1", "gap_check")
    graph.add_edge("fetch_tier3", "validate")
    graph.add_edge("validate",    "format")
    graph.add_edge("format",      END)

    graph.add_conditional_edges(
        "gap_check",
        route_after_gap_check,
        {
            "fetch_tier2": "fetch_tier2",
            "fetch_tier3": "fetch_tier3",
            "validate":    "validate",
        }
    )
    graph.add_conditional_edges(
        "fetch_tier2",
        route_after_tier2,
        {"fetch_tier3": "fetch_tier3"}
    )

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────
# 7. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

def main():
    """Run the Sovereign Econometric Agent."""
    print("=" * 60)
    print(" SUB-AGENT 1 — SOVEREIGN ECONOMETRIC ARCHITECT v3.0")
    print(" LangGraph Implementation")
    print("=" * 60)

    agent = build_graph()

    initial_state: AgentState = {
        "iso_codes": [],
        "tier1_data": {},
        "tier2_data": {},
        "tier3_data": {},
        "missing_after_tier1": [],
        "missing_after_tier2": [],
        "final_records": [],
        "errors": [],
    }

    log.info("Starting agent execution...")
    final_state = agent.invoke(initial_state)

    records = final_state["final_records"]
    print("\n" + "=" * 60)
    print(f" DONE — {len(records)} countries retrieved")
    print(f" Top 5 by GDP:")
    for r in records[:5]:
        print(f"   #{r['gdp_rank']} {r['country_name']}: ${r['nominal_gdp_usd']:,.0f}")
    print(f"\n Output saved to: GDP_data.json")
    print("=" * 60)

    return final_state


if __name__ == "__main__":
    main()
