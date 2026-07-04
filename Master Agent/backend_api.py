"""
backend_api.py — FastAPI backend for the OxiqAI Lead Generation Agent.

Wraps the existing phase_1..phase_5_5 pipeline functions (run_pipeline.py)
in a REST API so a separate frontend (React or otherwise) can drive the
same step-by-step pipeline the Streamlit dashboard (Exp_Full_Dash.py) does,
without needing Streamlit's session-state/rerun model.

Design notes
------------
- One in-memory `Session` holds a `PipelineState` + per-agent status, keyed
  by a session_id. This mirrors what st.session_state did per browser tab.
  There is no persistence: restarting the server loses in-flight sessions,
  same as restarting Streamlit did.
- Each phase can take real wall-clock time (LLM calls, scraping), so agent
  run endpoints kick off a background thread and return immediately; the
  frontend polls GET /sessions/{id}/status to render progress, same pattern
  the Streamlit app used with st.rerun() + time.sleep(1).
- No new pipeline logic is introduced here — phase_1_gdp_ranking ...
  phase_5_5_supabase_insert_leads are imported and called exactly as
  Exp_Full_Dash.py already calls them.

Run with:
    uvicorn backend_api:app --reload --port 8000
(from inside the "Master Agent" directory, so run_pipeline's path setup
 resolves the same way it does under Streamlit)
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
import uuid
from argparse import Namespace
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import run_pipeline
from run_pipeline import (
    phase_1_gdp_ranking,
    phase_2_city_segmentation,
    phase_3_zone_finding,
    phase_4_subarea_mapper,
    phase_4_5_supabase_insert,
    phase_5_lead_scraper,
    phase_5_5_supabase_insert_leads,
)
from orchestrator_utils import PipelineState

PROJECT_ROOT = run_pipeline.project_root

app = FastAPI(title="OxiqAI Lead Generation Agent API", version="1.0.0")

# Frontend runs on a different origin during development (Vite default: 5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # single-user local tool — see README for scope notes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory session store ─────────────────────────────────────────────
class Session:
    def __init__(self) -> None:
        self.id = str(uuid.uuid4())
        self.state = PipelineState()
        self.agent_status: dict = {1: "Pending", 2: "Pending", 3: "Pending", 4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"}
        self.running = False
        self.error: Optional[str] = None
        self.last_traceback: Optional[str] = None
        self.output_file: Optional[str] = None
        self.created_at = datetime.now().isoformat()


SESSIONS: dict[str, Session] = {}


def _get_session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Create one with POST /sessions.")
    return session


# ── Request bodies ──────────────────────────────────────────────────────
class Agent1Request(BaseModel):
    top_n: Optional[int] = None


class Agent2Request(BaseModel):
    selected_countries: list[str] = []


class Agent3Request(BaseModel):
    selected_cities: list[str] = []


class Agent4Request(BaseModel):
    selected_zones: list[str] = []


# ── Worker functions (mirror Exp_Full_Dash.py's run_agent_N exactly) ───
def _run_agent_1(session: Session, top_n: Optional[int]) -> None:
    args = Namespace(countries=None, top_n=top_n, refresh_gdp=False, cities=None, zones=None, max_scrolls=8, max_scrapers=3, skip_supabase=True)
    session.agent_status[1] = "Running"
    try:
        phase_1_gdp_ranking(session.state, args)
        session.agent_status[1] = "Done"
    except Exception as e:
        session.agent_status[1] = "Error"
        session.error = str(e)
        session.last_traceback = traceback.format_exc()
    finally:
        session.running = False


def _run_agent_2(session: Session, selected_countries: list[str]) -> None:
    if selected_countries:
        session.state.gdp_ranked_countries = [
            c for c in session.state.gdp_ranked_countries if c.get("country_name") in selected_countries
        ]
    session.agent_status[2] = "Running"
    try:
        phase_2_city_segmentation(session.state)
        session.agent_status[2] = "Done"
    except Exception as e:
        session.agent_status[2] = "Error"
        session.error = str(e)
        session.last_traceback = traceback.format_exc()
    finally:
        session.running = False


def _run_agent_3(session: Session, selected_cities: list[str]) -> None:
    if selected_cities:
        session.state.all_cities = [c for c in session.state.all_cities if c.get("city") in selected_cities]
    session.agent_status[3] = "Running"
    try:
        phase_3_zone_finding(session.state)
        session.agent_status[3] = "Done"
    except Exception as e:
        session.agent_status[3] = "Error"
        session.error = str(e)
        session.last_traceback = traceback.format_exc()
    finally:
        session.running = False


def _run_agent_4(session: Session, selected_zones: list[str]) -> None:
    session.agent_status[4] = "Running"
    try:
        if selected_zones:
            original = session.state.master_zone_registry
            filtered_registry = {}
            for (city, country), zones in original.items():
                matching = [z for z in zones if z in selected_zones]
                if matching:
                    filtered_registry[(city, country)] = matching
            session.state.master_zone_registry = filtered_registry
            phase_4_subarea_mapper(session.state)
            session.state.master_zone_registry = original
        else:
            phase_4_subarea_mapper(session.state)
        session.agent_status[4] = "Done"
    except Exception as e:
        session.agent_status[4] = "Error"
        session.error = str(e)
        session.last_traceback = traceback.format_exc()
    finally:
        session.running = False


def _run_agent_5(session: Session) -> None:
    session.agent_status[5] = "Running"
    try:
        phase_5_lead_scraper(session.state, 8, 3)
        session.state.finalize()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(PROJECT_ROOT, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
        import json
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(session.state.scraped_companies, f, indent=4, ensure_ascii=False)
        session.output_file = out_file
        session.agent_status[5] = "Done"
    except Exception as e:
        session.agent_status[5] = "Error"
        session.error = str(e)
        session.last_traceback = traceback.format_exc()
    finally:
        session.running = False


def _start_thread(session: Session, target, *args) -> None:
    if session.running:
        raise HTTPException(status_code=409, detail="A pipeline agent is already running for this session.")
    session.error = None
    session.last_traceback = None
    session.running = True
    threading.Thread(target=target, args=(session, *args), daemon=True).start()


# ── Session endpoints ───────────────────────────────────────────────────
@app.post("/sessions")
def create_session():
    session = Session()
    SESSIONS[session.id] = session
    return {"session_id": session.id, "created_at": session.created_at}


@app.get("/sessions/{session_id}/status")
def get_status(session_id: str):
    session = _get_session(session_id)
    return {
        "session_id": session.id,
        "running": session.running,
        "error": session.error,
        "agent_status": {str(k): v for k, v in session.agent_status.items()},
        "output_file": session.output_file,
    }


@app.delete("/sessions/{session_id}")
def reset_session(session_id: str):
    """Equivalent of the Streamlit app's 'Reset Pipeline State' button, but
    replaces the whole session (fresh PipelineState) rather than only
    clearing the running/error flags, so the frontend can offer a clean
    'Start Over' action."""
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    session = Session()
    session.id = session_id
    SESSIONS[session_id] = session
    return {"session_id": session.id, "reset": True}


# ── Agent run endpoints ─────────────────────────────────────────────────
@app.post("/sessions/{session_id}/agents/1/run")
def run_agent_1(session_id: str, body: Agent1Request):
    session = _get_session(session_id)
    _start_thread(session, _run_agent_1, body.top_n)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/2/run")
def run_agent_2(session_id: str, body: Agent2Request):
    session = _get_session(session_id)
    _start_thread(session, _run_agent_2, body.selected_countries)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/3/run")
def run_agent_3(session_id: str, body: Agent3Request):
    session = _get_session(session_id)
    _start_thread(session, _run_agent_3, body.selected_cities)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/4/run")
def run_agent_4(session_id: str, body: Agent4Request):
    session = _get_session(session_id)
    _start_thread(session, _run_agent_4, body.selected_zones)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/5/run")
def run_agent_5(session_id: str):
    session = _get_session(session_id)
    _start_thread(session, _run_agent_5)
    return {"status": "started"}


# ── Data endpoints (read current PipelineState, no side effects) ───────
@app.get("/sessions/{session_id}/data/countries")
def get_countries(session_id: str):
    session = _get_session(session_id)
    return session.state.gdp_ranked_countries


@app.get("/sessions/{session_id}/data/cities")
def get_cities(session_id: str):
    session = _get_session(session_id)
    return session.state.all_cities


@app.get("/sessions/{session_id}/data/zones")
def get_zones(session_id: str):
    session = _get_session(session_id)
    rows = []
    for (city, country), zones in session.state.master_zone_registry.items():
        for z in zones:
            rows.append({"country": country, "city": city, "zone_name": z})
    return rows


@app.get("/sessions/{session_id}/data/subareas")
def get_subareas(session_id: str):
    session = _get_session(session_id)
    return session.state.all_subarea_rows


@app.get("/sessions/{session_id}/data/companies")
def get_companies(
    session_id: str,
    country: Optional[str] = None,
    city: Optional[str] = None,
    zone: Optional[str] = None,
    subarea: Optional[str] = None,
):
    session = _get_session(session_id)
    companies = session.state.scraped_companies
    if subarea:
        companies = [c for c in companies if c.get("subarea_name") == subarea]
    elif zone:
        companies = [c for c in companies if c.get("zone_name") == zone]
    elif city:
        companies = [c for c in companies if c.get("city_name") == city]
    elif country:
        companies = [c for c in companies if c.get("country_name") == country]
    return companies


@app.get("/sessions/{session_id}/data/explorer-options")
def get_explorer_options(session_id: str, country: Optional[str] = None, city: Optional[str] = None, zone: Optional[str] = None):
    """Cascading dropdown options for the Data Explorer: countries always,
    cities if country given, zones if country+city given, subareas if all three given.
    Mirrors render_data_explorer()'s cascading selectboxes in Exp_Full_Dash.py."""
    session = _get_session(session_id)
    state = session.state

    countries = sorted({c.get("country") for c in state.all_cities if c.get("country")})

    cities = []
    if country:
        cities = sorted({c.get("city") for c in state.all_cities if c.get("country") == country and c.get("city")})

    zones = []
    if country and city:
        zones = state.master_zone_registry.get((city, country), [])

    subareas = []
    if country and city and zone:
        sa_list = state.master_subarea_registry.get((zone, city, country), [])
        subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

    return {"countries": countries, "cities": cities, "zones": zones, "subareas": subareas}


@app.get("/sessions/{session_id}/download")
def download_results(session_id: str):
    session = _get_session(session_id)
    if not session.output_file or not os.path.exists(session.output_file):
        raise HTTPException(status_code=404, detail="No results file available yet. Run Agent 5 first.")
    from fastapi.responses import FileResponse
    return FileResponse(session.output_file, filename="leads_results.json", media_type="application/json")


@app.get("/health")
def health():
    return {"status": "ok"}
