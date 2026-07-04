"""
backend_api.py — Production FastAPI Backend
============================================
Uses PipelineOrchestrator for one-click automatic pipeline execution.
Provides SSE (Server-Sent Events) for live log streaming.

Endpoints:
  POST /sessions                            – create session
  GET  /sessions/{id}/status               – poll live status + metrics
  DELETE /sessions/{id}                     – reset session
  POST /sessions/{id}/pipeline/run         – start FULL auto-pipeline
  POST /sessions/{id}/pipeline/stop        – graceful stop
  GET  /sessions/{id}/pipeline/logs/stream – SSE live log stream
  GET  /sessions/{id}/pipeline/logs        – all logs (JSON array)
  POST /sessions/{id}/agents/{n}/run       – run individual agent
  GET  /sessions/{id}/data/*               – data queries
  GET  /sessions/{id}/results              – inline JSON results (no file needed)
  GET  /sessions/{id}/download             – download results JSON file
  GET  /health                             – health check

Run:
  uvicorn backend_api:app --reload --port 8000
(from inside "Master Agent/" directory)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import traceback
import uuid
from argparse import Namespace
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Path bootstrap ──────────────────────────────────────────────────────────
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
from pipeline_orchestrator import PipelineOrchestrator

PROJECT_ROOT = run_pipeline.project_root

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="OxiqAI Lead Generation — Production API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════
#  Session model — now holds a PipelineOrchestrator + fallback PipelineState
# ═══════════════════════════════════════════════════════════════════════════

class Session:
    def __init__(self) -> None:
        self.id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()

        # Production orchestrator (used by /pipeline/run)
        self.orchestrator = PipelineOrchestrator()

        # Legacy per-agent state (used by /agents/{n}/run)
        self.state = PipelineState()
        self.agent_status: dict = {
            "1": "Pending", "2": "Pending", "3": "Pending",
            "4": "Pending", "5": "Pending",
        }
        self._agent_running = False
        self._agent_error: Optional[str] = None
        self._agent_tb: Optional[str] = None
        self.output_file: Optional[str] = None


SESSIONS: dict[str, Session] = {}


def _get_session(session_id: str) -> Session:
    s = SESSIONS.get(session_id)
    if s is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Create one with POST /sessions.",
        )
    return s


# ═══════════════════════════════════════════════════════════════════════════
#  Request bodies
# ═══════════════════════════════════════════════════════════════════════════

class PipelineRunRequest(BaseModel):
    top_n: Optional[int] = None
    selected_countries: list[str] = []
    selected_cities: list[str] = []
    selected_zones: list[str] = []
    max_scrolls: int = 8
    max_scrapers: int = 3
    skip_supabase: bool = False


class Agent1Request(BaseModel):
    top_n: Optional[int] = None
    countries: Optional[list[str]] = None


class Agent2Request(BaseModel):
    selected_countries: list[str] = []


class Agent3Request(BaseModel):
    selected_cities: list[str] = []


class Agent4Request(BaseModel):
    selected_zones: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════
#  Session endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/sessions")
def create_session():
    s = Session()
    SESSIONS[s.id] = s
    return {"session_id": s.id, "created_at": s.created_at}


@app.get("/sessions/{session_id}/status")
def get_status(session_id: str):
    s = _get_session(session_id)
    orch = s.orchestrator

    # If orchestrator is active, return its rich status
    if orch.metrics is not None:
        orch_status = orch.get_status()
        # Map orchestrator agent statuses back to the legacy agent_status dict
        for aid, am in orch_status["agents"].items():
            s.agent_status[str(aid)] = am["status"].capitalize().replace("Done", "Done").replace("Failed", "Error")
        if orch.metrics.output_file:
            s.output_file = orch.metrics.output_file

        return {
            "session_id": s.id,
            "running": orch.is_running(),
            "error": orch_status.get("error"),
            "agent_status": s.agent_status,
            "output_file": s.output_file,
            # Extra production fields
            "pipeline_status": orch_status["status"],
            "elapsed": orch_status.get("elapsed"),
            "counts": orch_status.get("counts", {}),
            "system": orch_status.get("system", {}),
            "failed_agent": orch_status.get("failed_agent"),
            "agents_detail": orch_status.get("agents", {}),
        }

    # Fallback: legacy per-agent status
    return {
        "session_id": s.id,
        "running": s._agent_running,
        "error": s._agent_error,
        "agent_status": s.agent_status,
        "output_file": s.output_file,
        "pipeline_status": "idle",
        "elapsed": None,
        "counts": {},
        "system": {},
        "failed_agent": None,
        "agents_detail": {},
    }


@app.delete("/sessions/{session_id}")
def reset_session(session_id: str):
    if session_id in SESSIONS:
        old = SESSIONS[session_id]
        if old.orchestrator.is_running():
            old.orchestrator.stop()
        del SESSIONS[session_id]
    s = Session()
    s.id = session_id
    SESSIONS[session_id] = s
    return {"session_id": s.id, "reset": True}


# ═══════════════════════════════════════════════════════════════════════════
#  Full Pipeline — One-click auto-pipeline using PipelineOrchestrator
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/sessions/{session_id}/pipeline/run")
def run_full_pipeline(session_id: str, body: PipelineRunRequest):
    """
    Starts the complete automatic pipeline: Agent 1 → 2 → 3 → 4 → Execution Engine.
    All agents run sequentially and automatically.
    Poll GET /sessions/{id}/status for live progress.
    Stream logs via GET /sessions/{id}/pipeline/logs/stream (SSE).
    """
    s = _get_session(session_id)
    if s.orchestrator.is_running():
        raise HTTPException(409, "Pipeline is already running.")
    s.orchestrator.start(
        top_n=body.top_n,
        selected_countries=body.selected_countries,
        selected_cities=body.selected_cities,
        selected_zones=body.selected_zones,
        max_scrolls=body.max_scrolls,
        max_scrapers=body.max_scrapers,
        skip_supabase=body.skip_supabase,
    )
    return {
        "status": "started",
        "message": "Full pipeline started automatically. "
                   "Poll /status or stream /pipeline/logs/stream for progress.",
    }


@app.post("/sessions/{session_id}/pipeline/stop")
def stop_pipeline(session_id: str):
    s = _get_session(session_id)
    s.orchestrator.stop()
    return {"status": "stop_requested"}


# ═══════════════════════════════════════════════════════════════════════════
#  Live Log Streaming — SSE
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/sessions/{session_id}/pipeline/logs/stream")
async def stream_logs(session_id: str):
    """
    Server-Sent Events endpoint. Each event is a JSON log entry:
      data: {"ts":"08:12:34","level":"INFO","agent":"Agent 2","message":"✓ Mumbai"}
    """
    s = _get_session(session_id)
    log_queue = s.orchestrator.log_bus.subscribe()

    async def _generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                # Drain any queued entries
                sent_any = False
                while log_queue:
                    entry = log_queue.popleft()
                    data = json.dumps(entry.to_dict())
                    yield f"data: {data}\n\n"
                    sent_any = True

                # Send keep-alive comment every 15s of silence
                if not sent_any:
                    yield ": keep-alive\n\n"

                await asyncio.sleep(0.3)

                # End stream when pipeline finishes and queue is empty
                if (not s.orchestrator.is_running()
                        and len(log_queue) == 0
                        and s.orchestrator.metrics is not None
                        and s.orchestrator.metrics.status in ("done", "failed", "stopped")):
                    yield "data: {\"ts\":\"\",\"level\":\"EOF\",\"agent\":\"SYSTEM\",\"message\":\"Pipeline finished\"}\n\n"
                    break
        finally:
            s.orchestrator.log_bus.unsubscribe(log_queue)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sessions/{session_id}/pipeline/logs")
def get_logs(session_id: str):
    """Return all log entries accumulated so far as a JSON array."""
    s = _get_session(session_id)
    return s.orchestrator.log_bus.history()


# ═══════════════════════════════════════════════════════════════════════════
#  Individual Agent endpoints (legacy manual mode)
# ═══════════════════════════════════════════════════════════════════════════

def _start_agent_thread(s: Session, target, *args) -> None:
    if s._agent_running:
        raise HTTPException(409, "An agent is already running.")
    s._agent_error = None
    s._agent_tb = None
    s._agent_running = True
    threading.Thread(target=target, args=(s, *args), daemon=True).start()


def _run_agent_1(s: Session, top_n: Optional[int], countries: Optional[list] = None) -> None:
    s.agent_status["1"] = "Running"
    try:
        args = Namespace(
            countries=",".join(countries) if countries else None,
            top_n=top_n, refresh_gdp=False,
            cities=None, zones=None, max_scrolls=8, max_scrapers=3, skip_supabase=True,
        )
        phase_1_gdp_ranking(s.state, args)
        s.agent_status["1"] = "Done"
    except Exception as e:
        s.agent_status["1"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
    finally:
        s._agent_running = False


def _run_agent_2(s: Session, selected_countries: list) -> None:
    if selected_countries:
        s.state.gdp_ranked_countries = [
            c for c in s.state.gdp_ranked_countries
            if c.get("country_name") in selected_countries
        ]
    s.agent_status["2"] = "Running"
    try:
        phase_2_city_segmentation(s.state)
        s.agent_status["2"] = "Done"
    except Exception as e:
        s.agent_status["2"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
    finally:
        s._agent_running = False


def _run_agent_3(s: Session, selected_cities: list) -> None:
    if selected_cities:
        s.state.all_cities = [c for c in s.state.all_cities
                              if c.get("city") in selected_cities]
    s.agent_status["3"] = "Running"
    try:
        phase_3_zone_finding(s.state)
        s.agent_status["3"] = "Done"
    except Exception as e:
        s.agent_status["3"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
    finally:
        s._agent_running = False


def _run_agent_4(s: Session, selected_zones: list) -> None:
    s.agent_status["4"] = "Running"
    try:
        if selected_zones:
            orig = s.state.master_zone_registry
            s.state.master_zone_registry = {
                (city, co): [z for z in zones if z in selected_zones]
                for (city, co), zones in orig.items()
                if any(z in selected_zones for z in zones)
            }
        phase_4_subarea_mapper(s.state)
        s.agent_status["4"] = "Done"
    except Exception as e:
        s.agent_status["4"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
    finally:
        s._agent_running = False


def _run_agent_5(s: Session) -> None:
    s.agent_status["5"] = "Running"
    try:
        phase_5_lead_scraper(s.state, 8, 3)
        phase_4_5_supabase_insert(s.state, skip_supabase=False)
        phase_5_5_supabase_insert_leads(s.state, skip_supabase=False)
        s.state.finalize()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(PROJECT_ROOT, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(s.state.scraped_companies, f, indent=4, ensure_ascii=False)
        s.output_file = out_file
        print(f"[Agent 5] Saved {len(s.state.scraped_companies)} leads → {out_file}")
        s.agent_status["5"] = "Done"
    except Exception as e:
        s.agent_status["5"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        print(f"[Agent 5] ERROR: {e}\n{s._agent_tb}")
    finally:
        s._agent_running = False


@app.post("/sessions/{session_id}/agents/1/run")
def run_agent_1(session_id: str, body: Agent1Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_1, body.top_n, body.countries)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/2/run")
def run_agent_2(session_id: str, body: Agent2Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_2, body.selected_countries)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/3/run")
def run_agent_3(session_id: str, body: Agent3Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_3, body.selected_cities)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/4/run")
def run_agent_4(session_id: str, body: Agent4Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_4, body.selected_zones)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/5/run")
def run_agent_5(session_id: str):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_5)
    return {"status": "started"}


# ═══════════════════════════════════════════════════════════════════════════
#  Data endpoints
# ═══════════════════════════════════════════════════════════════════════════

def _active_state(s: Session) -> PipelineState:
    """Return orchestrator state if active, else legacy state."""
    if s.orchestrator.metrics is not None and s.orchestrator._state is not None:
        return s.orchestrator._state
    return s.state


@app.get("/sessions/{session_id}/data/countries")
def get_countries(session_id: str):
    return _active_state(_get_session(session_id)).gdp_ranked_countries


@app.get("/sessions/{session_id}/data/cities")
def get_cities(session_id: str):
    return _active_state(_get_session(session_id)).all_cities


@app.get("/sessions/{session_id}/data/zones")
def get_zones(session_id: str):
    state = _active_state(_get_session(session_id))
    rows = []
    for (city, country), zones in state.master_zone_registry.items():
        for z in zones:
            rows.append({"country": country, "city": city, "zone_name": z})
    return rows


@app.get("/sessions/{session_id}/data/subareas")
def get_subareas(session_id: str):
    return _active_state(_get_session(session_id)).all_subarea_rows


@app.get("/sessions/{session_id}/data/companies")
def get_companies(
    session_id: str,
    country: Optional[str] = None,
    city: Optional[str] = None,
    zone: Optional[str] = None,
    subarea: Optional[str] = None,
):
    companies = _active_state(_get_session(session_id)).scraped_companies
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
def get_explorer_options(
    session_id: str,
    country: Optional[str] = None,
    city: Optional[str] = None,
    zone: Optional[str] = None,
):
    state = _active_state(_get_session(session_id))
    countries = sorted({c.get("country") for c in state.all_cities if c.get("country")})
    cities = []
    if country:
        cities = sorted({c.get("city") for c in state.all_cities
                         if c.get("country") == country and c.get("city")})
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
    s = _get_session(session_id)
    path = s.output_file
    if not path and s.orchestrator.metrics:
        path = s.orchestrator.metrics.output_file
    if not path or not os.path.exists(path):
        raise HTTPException(404, "No results file yet. Run the pipeline first.")
    from fastapi.responses import FileResponse
    return FileResponse(path, filename="leads_results.json", media_type="application/json")


@app.get("/sessions/{session_id}/results")
def get_results_inline(session_id: str):
    """
    Return all scraped companies as inline JSON — no file download needed.
    Useful for displaying results in the frontend directly.
    Returns count, pipeline_status, and the full companies list.
    """
    s = _get_session(session_id)
    state = _active_state(s)
    companies = state.scraped_companies or []
    pipeline_status = "idle"
    if s.orchestrator.metrics:
        pipeline_status = s.orchestrator.metrics.status
    return {
        "count": len(companies),
        "pipeline_status": pipeline_status,
        "source": "live_state",
        "companies": companies,
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=True, app_dir=BASE_DIR)

