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
import time
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

# Also expose the project root for adaptive_concurrency
PROJECT_PARENT = os.path.dirname(BASE_DIR)
if PROJECT_PARENT not in sys.path:
    sys.path.insert(0, PROJECT_PARENT)

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
from pipeline_orchestrator import PipelineOrchestrator, AgentMetrics, LogBus, LogEntry

# Adaptive concurrency health tracking (may not exist yet — soft import)
try:
    from adaptive_concurrency import all_health_snapshots as _all_health_snapshots
    _ADAPTIVE_AVAILABLE = True
except ImportError:
    _ADAPTIVE_AVAILABLE = False
    def _all_health_snapshots():
        return []

# Agent 3 live metrics (may not exist yet — soft import)
try:
    import sys as _sys
    _sub3_path = os.path.join(os.path.dirname(BASE_DIR), "SUB AGENT 3 zone finder")
    if _sub3_path not in _sys.path:
        _sys.path.insert(0, _sub3_path)
    from zone_metrics import ZONE_METRICS as _ZONE_METRICS
    _ZONE_METRICS_AVAILABLE = True
except Exception:
    _ZONE_METRICS_AVAILABLE = False
    class _NullZoneMetrics:
        def to_dict(self):
            return {"error": "zone_metrics module not available"}
    _ZONE_METRICS = _NullZoneMetrics()  # type: ignore

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

        # Timer + live-log support for manual (legacy) per-agent runs.
        # Reuses the same AgentMetrics/LogBus shapes the orchestrator uses,
        # so the frontend's agents_detail / SSE log handling works identically
        # whether a run came from Auto (/pipeline/run) or Manual (/agents/N/run).
        self.agent_metrics: dict[str, AgentMetrics] = {}
        self.log_bus = LogBus()
        self._manual_stop_event = threading.Event()

        # Which LLM/search providers have hit a rate limit / quota error during
        # this session. Surfaced in /status as rate_limited_providers so the
        # frontend can show a warning indicator on the provider toggle, and
        # logged as a distinct RATE_LIMIT log entry. Cleared on session reset.
        self.rate_limited_providers: set[str] = set()


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
    provider: str = "groq"  # any key in PROVIDERS registry — groq/gemini/openai/gpt-4o/claude/mistral/etc.


class Agent3Request(BaseModel):
    selected_cities: list[str] = []


class Agent4Request(BaseModel):
    selected_zones: list[str] = []
    provider: str = "groq"  # any key in PROVIDERS registry — groq/gemini/openai/gpt-4o/claude/mistral/etc.


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
            "rate_limited_providers": sorted(s.rate_limited_providers),
        }

    # Fallback: legacy per-agent status (Manual mode - /agents/N/run)
    return {
        "session_id": s.id,
        "running": False,
        "error": None,
        "agent_status": s.agent_status,
        "output_file": s.output_file,
    }

@app.get("/debug")
def get_debug():
    res = {}
    for sid, s in SESSIONS.items():
        if s.orchestrator and s.orchestrator.metrics:
            res[sid] = {
                "active_workers": {k: v.active_instances for k, v in s.orchestrator.metrics.agents.items()},
                "input_counts": {k: v.input_count for k, v in s.orchestrator.metrics.agents.items()}
            }
    return res
    return {
        "session_id": s.id,
        "running": s._agent_running,
        "error": s._agent_error,
        "agent_status": s.agent_status,
        "output_file": s.output_file,
        "pipeline_status": "idle",
        "elapsed": None,
        "counts": {
            "countries": len(s.state.gdp_ranked_countries),
            "cities": len(s.state.all_cities),
            "zones": sum(len(z) for z in s.state.master_zone_registry.values()),
            "subareas": len(s.state.all_subarea_rows),
            "companies": len(s.state.scraped_companies),
        },
        "system": {},
        "failed_agent": None,
        # Real per-agent timer/output data for Manual mode, same shape the
        # orchestrator produces - AgentStageRow renders elapsed/output_count
        # identically regardless of which mode ran the agent.
        "agents_detail": {aid: am.to_dict() for aid, am in s.agent_metrics.items()},
        # Which providers have hit a rate limit this session, so the frontend
        # can show a warning triangle on that provider's toggle button.
        "rate_limited_providers": sorted(s.rate_limited_providers),
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
    """Stops whichever mode is currently running: the orchestrator (Auto)
    or the in-flight manual agent (Manual - sets _manual_stop_event, checked
    inside Agent 3's retry loops so it can bail out between attempts instead
    of only between whole agents)."""
    s = _get_session(session_id)
    s.orchestrator.stop()
    s._manual_stop_event.set()
    return {"status": "stop_requested"}


# ═══════════════════════════════════════════════════════════════════════════
#  Live Log Streaming — SSE
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/sessions/{session_id}/pipeline/logs/stream")
async def stream_logs(session_id: str):
    """
    Server-Sent Events endpoint. Each event is a JSON log entry:
      data: {"ts":"08:12:34","level":"INFO","agent":"Agent 2","message":"✓ Mumbai"}

    Picks whichever log bus is actually active for this session: the
    orchestrator's (Auto / full-pipeline runs) if it has ever been used,
    otherwise the session's own log_bus (Manual / per-agent runs). This is
    decided once at connect time - a session normally sticks to one mode.
    """
    s = _get_session(session_id)
    use_orchestrator = s.orchestrator.metrics is not None
    bus = s.orchestrator.log_bus if use_orchestrator else s.log_bus
    log_queue = bus.subscribe()

    def _finished() -> bool:
        if use_orchestrator:
            return (not s.orchestrator.is_running()
                    and s.orchestrator.metrics is not None
                    and s.orchestrator.metrics.status in ("done", "failed", "stopped"))
        return not s._agent_running

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

                # End stream when the active run finishes and queue is empty
                if _finished() and len(log_queue) == 0:
                    yield "data: {\"ts\":\"\",\"level\":\"EOF\",\"agent\":\"SYSTEM\",\"message\":\"Run finished\"}\n\n"
                    break
        finally:
            bus.unsubscribe(log_queue)

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
    bus = s.orchestrator.log_bus if s.orchestrator.metrics is not None else s.log_bus
    return bus.history()


# ═══════════════════════════════════════════════════════════════════════════
#  Individual Agent endpoints (legacy manual mode)
# ═══════════════════════════════════════════════════════════════════════════

AGENT_NAMES = {
    "1": "Agent 1 — Country Discovery",
    "2": "Agent 2 — City Discovery",
    "3": "Agent 3 — Commercial Zone Discovery",
    "4": "Agent 4 — Sub-Area Mapping",
    "5": "Execution Engine — Company Discovery",
}


def _manual_log(s: Session, agent_id: str, level: str, message: str) -> None:
    """Emit a log entry to this session's log bus - same LogEntry shape the
    orchestrator uses, so the existing SSE stream / log console work
    unchanged for manual per-agent runs too."""
    entry = LogEntry(
        ts=datetime.now().strftime("%H:%M:%S"),
        level=level,
        agent=AGENT_NAMES.get(agent_id, f"Agent {agent_id}"),
        message=message,
    )
    s.log_bus.emit(entry)


def _mark_rate_limited(s: Session, agent_id: str, provider: str, detail: str = "") -> None:
    """Record that `provider` (e.g. "groq", "gemini", "tavily") hit a rate
    limit / quota error during this session, and log it as a distinct
    RATE_LIMIT entry (not just WARN) so the frontend can style it and show
    the warning triangle on that provider's toggle button. Call this from
    each agent's own existing 429/quota detection - it doesn't do detection
    itself, just records + surfaces what was already detected."""
    s.rate_limited_providers.add(provider.lower())
    msg = f"{provider.upper()} rate limit hit" + (f" — {detail}" if detail else "")
    _manual_log(s, agent_id, "RATE_LIMIT", msg)


def _manual_start(s: Session, agent_id: str) -> AgentMetrics:
    m = AgentMetrics(agent_id=agent_id, agent_name=AGENT_NAMES.get(agent_id, f"Agent {agent_id}"),
                      status="running", start_time=time.time())
    s.agent_metrics[agent_id] = m
    _manual_log(s, agent_id, "STAGE", f"{AGENT_NAMES.get(agent_id, agent_id)} started")
    return m


def _manual_finish(s: Session, m: AgentMetrics, success: bool, output_count: int = 0) -> None:
    m.end_time = time.time()
    m.status = "done" if success else "failed"
    m.output_count = output_count
    level = "SUCCESS" if success else "ERROR"
    verb = "completed" if success else "failed"
    _manual_log(s, m.agent_id, level, f"{m.agent_name} {verb} — {m.elapsed}"
                + (f", {output_count} items" if success else ""))


def _start_agent_thread(s: Session, target, *args) -> None:
    if s._agent_running:
        raise HTTPException(409, "An agent is already running.")
    s._agent_error = None
    s._agent_tb = None
    s._agent_running = True
    s._manual_stop_event.clear()
    threading.Thread(target=target, args=(s, *args), daemon=True).start()


def _run_agent_1(s: Session, top_n: Optional[int], countries: Optional[list] = None) -> None:
    s.agent_status["1"] = "Running"
    m = _manual_start(s, "1")
    try:
        args = Namespace(
            countries=",".join(countries) if countries else None,
            top_n=top_n, refresh_gdp=False,
            cities=None, zones=None, max_scrolls=8, max_scrapers=3, skip_supabase=True,
        )
        phase_1_gdp_ranking(s.state, args)
        s.agent_status["1"] = "Done"
        _manual_finish(s, m, True, len(s.state.gdp_ranked_countries))
    except Exception as e:
        s.agent_status["1"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        m.errors.append(str(e))
        _manual_finish(s, m, False)
    finally:
        s._agent_running = False


def _run_agent_2(s: Session, selected_countries: list, provider: str = "groq") -> None:
    if selected_countries:
        if not s.state.gdp_ranked_countries:
            s.state.gdp_ranked_countries = [{"country_name": c, "gdp_rank": i+1} for i, c in enumerate(selected_countries)]
        else:
            s.state.gdp_ranked_countries = [
                c for c in s.state.gdp_ranked_countries
                if (c.get("country_name") if isinstance(c, dict) else c) in selected_countries
            ]
    s.agent_status["2"] = "Running"
    m = _manual_start(s, "2")
    try:
        import city_segmenters_code
        city_segmenters_code.set_rate_limit_callback(
            lambda p, d: _mark_rate_limited(s, "2", p, d)
        )
        phase_2_city_segmentation(s.state, provider=provider, stop_event=s._manual_stop_event)
        if s._manual_stop_event.is_set():
            s.agent_status["2"] = "Error"
            m.errors.append("Stopped by user request.")
            _manual_finish(s, m, False, len(s.state.all_cities))
        else:
            s.agent_status["2"] = "Done"
            _manual_finish(s, m, True, len(s.state.all_cities))
    except Exception as e:
        s.agent_status["2"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        m.errors.append(str(e))
        _manual_finish(s, m, False)
    finally:
        s._agent_running = False


def _run_agent_3(s: Session, selected_cities: list) -> None:
    if selected_cities:
        if not s.state.all_cities:
            s.state.all_cities = [{"city": c, "country": "Unknown", "tier": 1} for c in selected_cities]
        else:
            s.state.all_cities = [c for c in s.state.all_cities
                                  if c.get("city") in selected_cities]
    s.agent_status["3"] = "Running"
    m = _manual_start(s, "3")
    try:
        import zone_finders_code
        zone_finders_code.set_rate_limit_callback(
            lambda p, d: _mark_rate_limited(s, "3", p, d)
        )
        phase_3_zone_finding(s.state, stop_event=s._manual_stop_event)
        total_zones = sum(len(z) for z in s.state.master_zone_registry.values())
        if s._manual_stop_event.is_set():
            s.agent_status["3"] = "Error"
            m.errors.append("Stopped by user request.")
            _manual_finish(s, m, False, total_zones)
        else:
            s.agent_status["3"] = "Done"
            _manual_finish(s, m, True, total_zones)
    except Exception as e:
        s.agent_status["3"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        m.errors.append(str(e))
        _manual_finish(s, m, False)
    finally:
        s._agent_running = False


def _run_agent_4(s: Session, selected_zones: list, provider: str = "groq") -> None:
    s.agent_status["4"] = "Running"
    m = _manual_start(s, "4")
    try:
        import main as agent4_main
        agent4_main.set_rate_limit_callback(
            lambda p, d: _mark_rate_limited(s, "4", p, d)
        )
        if selected_zones:
            if not s.state.master_zone_registry:
                # If state is empty, mock a dummy registry to allow the agent to run
                s.state.master_zone_registry = {("Unknown City", "Unknown Country"): selected_zones}
            else:
                orig = s.state.master_zone_registry
                s.state.master_zone_registry = {
                    (city, co): [z for z in zones if z in selected_zones]
                    for (city, co), zones in orig.items()
                    if any(z in selected_zones for z in zones)
                }
        phase_4_subarea_mapper(s.state, provider=provider, stop_event=s._manual_stop_event)
        if s._manual_stop_event.is_set():
            s.agent_status["4"] = "Error"
            m.errors.append("Stopped by user request.")
            _manual_finish(s, m, False, len(s.state.all_subarea_rows))
        else:
            s.agent_status["4"] = "Done"
            _manual_finish(s, m, True, len(s.state.all_subarea_rows))
    except Exception as e:
        s.agent_status["4"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        m.errors.append(str(e))
        _manual_finish(s, m, False)
    finally:
        s._agent_running = False


def _run_agent_5(s: Session) -> None:
    s.agent_status["5"] = "Running"
    m = _manual_start(s, "5")
    try:
        phase_5_lead_scraper(s.state, 8, 3, stop_event=s._manual_stop_event)
        if s._manual_stop_event.is_set():
            s.agent_status["5"] = "Error"
            m.errors.append("Stopped by user request.")
            _manual_finish(s, m, False, len(s.state.scraped_companies))
        else:
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
            _manual_finish(s, m, True, len(s.state.scraped_companies))
    except Exception as e:
        s.agent_status["5"] = "Error"
        s._agent_error = str(e)
        s._agent_tb = traceback.format_exc()
        print(f"[Agent 5] ERROR: {e}\n{s._agent_tb}")
        m.errors.append(str(e))
        _manual_finish(s, m, False)
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
    _start_agent_thread(s, _run_agent_2, body.selected_countries, body.provider)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/3/run")
def run_agent_3(session_id: str, body: Agent3Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_3, body.selected_cities)
    return {"status": "started"}


@app.post("/sessions/{session_id}/agents/4/run")
def run_agent_4(session_id: str, body: Agent4Request):
    s = _get_session(session_id)
    _start_agent_thread(s, _run_agent_4, body.selected_zones, body.provider)
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


@app.get("/provider-health")
def provider_health():
    """
    Returns live health and concurrency data for every LLM/search provider
    that has processed at least one request this process lifetime.

    Response shape (per provider):
    {
        "provider":         "groq",
        "health_score":     0.87,
        "workers":          8,
        "max_workers":      12,
        "success_rate":     0.93,
        "rate_429":         0.04,
        "timeout_rate":     0.01,
        "avg_latency":      1.8,
        "baseline_latency": 1.5,
        "latency_ratio":    1.2,
        "total_calls":      142,
        "retry_count":      6,
        "fallback_count":   1,
        "window_size":      50,
        "status":           "HEALTHY",
        "model":            "llama-3.3-70b-versatile"
    }
    Consumed by the frontend to render per-provider health badges.
    """
    return _all_health_snapshots()


@app.get("/agent3/metrics")
def agent3_metrics():
    """
    Returns live Agent 3 (Zone Finder) execution metrics.
    Updated in real-time as the swarm processes cities.

    Response shape:
    {
        "cities_total":        25,
        "cities_pending":       5,
        "cities_running":       3,
        "cities_completed":    16,
        "cities_failed":        1,
        "zones_found":        192,
        "avg_zones_per_city": 12.0,
        "avg_processing_time": 38.4,   -- seconds
        "avg_queue_wait":       1.2,   -- seconds
        "elapsed_sec":        612.0,
        "retries":              7,
        "fallback_count":       1,
        "active_workers":       3,
        "queue_size":           5,
        "provider_usage":     { "groq": 14, "gemini": 3 },
        "failed_cities":      [ { "city": "Delhi", "reason": "..." } ]
    }
    """
    return _ZONE_METRICS.to_dict()


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=True, app_dir=BASE_DIR)

