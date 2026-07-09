"""
pipeline_orchestrator.py — Production-Grade Pipeline Orchestrator
==================================================================
Wraps run_pipeline.py phase functions with:
  - Structured stage-by-stage logging
  - Live SSE-streamable log queue
  - Per-agent timing, counts, error tracking
  - Checkpoint save/resume
  - Retry on failure
  - Graceful shutdown
  - System metrics (CPU, memory)
  - Full execution report generation
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import threading
import psutil
import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from argparse import Namespace

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

# Configure logging to use UTF-8 so Unicode log messages (✓, ═, …) never
# raise UnicodeEncodeError on Windows CP1252 terminals.
try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(stream=sys.stdout)
        ],
    )
    # Force UTF-8 on the root handler if possible
    for _h in logging.root.handlers:
        if hasattr(_h, 'stream') and hasattr(_h.stream, 'reconfigure'):
            try:
                _h.stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
except Exception:
    pass


# ─── Path bootstrap (same as run_pipeline.py) ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)  # project root

for _p in [
    _HERE,
    os.path.join(_PROJ, "SUB AGENT 1"),
    os.path.join(_PROJ, "SUB AGENT 2"),
    os.path.join(_PROJ, "SUB AGENT 3 zone finder"),
    os.path.join(_PROJ, "SUB_AGENT 4 sub area mapper"),
    os.path.join(_PROJ, "execution_engine"),
    _PROJ,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJ, ".env"))
# Also load from each agent's .env so all keys are present
for _env in [
    os.path.join(_PROJ, "SUB AGENT 1", ".env"),
    os.path.join(_PROJ, "SUB AGENT 2", ".env"),
    os.path.join(_PROJ, "SUB AGENT 3 zone finder", ".env"),
    os.path.join(_PROJ, "SUB_AGENT 4 sub area mapper", ".env"),
    os.path.join(_PROJ, "execution_engine", ".env"),
]:
    if os.path.exists(_env):
        load_dotenv(_env, override=False)

# ─── Lazy imports of pipeline phases ──────────────────────────────────────
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

# ─── Constants ────────────────────────────────────────────────────────────
CHECKPOINT_FILE = os.path.join(_HERE, "pipeline_checkpoint.json")
REPORT_DIR = os.path.join(_PROJ, "outputs")
MAX_LOG_ENTRIES = 2000


# ═══════════════════════════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LogEntry:
    ts: str
    level: str          # INFO | WARN | ERROR | SUCCESS | STAGE | METRIC
    agent: str
    message: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AgentMetrics:
    agent_id: str
    agent_name: str
    status: str = "pending"      # pending | running | done | failed | skipped
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    input_count: int = 0
    output_count: int = 0
    active_instances: int = 0
    error_count: int = 0
    retry_count: int = 0
    errors: List[str] = field(default_factory=list)
    items_in: List[str] = field(default_factory=list)
    items_out: List[str] = field(default_factory=list)
    # Not serialized
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, init=False)

    def change_active_instances(self, delta: int) -> None:
        with self._lock:
            self.active_instances = max(0, self.active_instances + delta)

    def reset_active_instances(self) -> None:
        with self._lock:
            self.active_instances = 0

    def record_output(self, new_items: List[str]) -> None:
        with self._lock:
            self.items_out.extend(new_items)
            self.output_count = len(self.items_out)

    @property
    def elapsed(self) -> str:
        if self.start_time is None:
            return "—"
        end = self.end_time or time.time()
        secs = end - self.start_time
        if secs < 60:
            return f"{secs:.1f}s"
        return f"{int(secs//60)}m {int(secs%60)}s"

    def to_dict(self) -> Dict:
        # Build dict manually without deepcopy to avoid TypeError on threading.Lock
        d = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "_lock"
        }
        d["elapsed"] = self.elapsed
        return d


@dataclass
class PipelineMetrics:
    pipeline_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "initializing"   # initializing | running | done | failed | stopped
    agents: Dict[str, AgentMetrics] = field(default_factory=dict)

    # Counts
    countries: int = 0
    cities: int = 0
    zones: int = 0
    subareas: int = 0
    companies_raw: int = 0
    companies_deduped: int = 0
    duplicates_removed: int = 0
    invalid_records: int = 0
    supabase_inserted: int = 0

    # System
    peak_cpu: float = 0.0
    peak_mem_mb: float = 0.0

    output_file: Optional[str] = None
    error: Optional[str] = None
    failed_agent: Optional[str] = None

    @property
    def elapsed(self) -> str:
        end = self.end_time or time.time()
        secs = end - self.start_time
        if secs < 60:
            return f"{secs:.1f}s"
        mins = int(secs // 60)
        s = int(secs % 60)
        if mins < 60:
            return f"{mins}m {s}s"
        return f"{mins//60}h {mins%60}m {s}s"

    def to_dict(self) -> Dict:
        # Build dict manually to avoid asdict()'s deep-copy, which crashes on
        # the threading.Lock inside each AgentMetrics._lock field.
        d = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "agents"
        }
        d["elapsed"] = self.elapsed
        # Delegate agent serialization to AgentMetrics.to_dict() which already
        # handles the Lock exclusion correctly.
        d["agents"] = {k: v.to_dict() for k, v in self.agents.items()}
        return d


# ═══════════════════════════════════════════════════════════════════════════
#  Live Log Bus  (thread-safe ring-buffer + subscribers)
# ═══════════════════════════════════════════════════════════════════════════

class LogBus:
    """Thread-safe broadcast log bus. Subscribers (SSE clients) get all new entries."""

    def __init__(self, maxlen: int = MAX_LOG_ENTRIES):
        self._lock = threading.Lock()
        self._history: deque[LogEntry] = deque(maxlen=maxlen)
        self._subs: List[deque] = []

    def subscribe(self) -> deque:
        q: deque = deque()
        # pre-fill with history so new subscribers get past events
        with self._lock:
            q.extend(self._history)
            self._subs.append(q)
        return q

    def unsubscribe(self, q: deque) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def emit(self, entry: LogEntry) -> None:
        with self._lock:
            self._history.append(entry)
            for q in self._subs:
                q.append(entry)

    def history(self) -> List[Dict]:
        with self._lock:
            return [e.to_dict() for e in self._history]


# ═══════════════════════════════════════════════════════════════════════════
#  Logging Interceptor
# ═══════════════════════════════════════════════════════════════════════════

class LogBusHandler(logging.Handler):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self._local = threading.local()

    def emit(self, record):
        if getattr(self._local, 'emitting', False):
            return
        self._local.emitting = True
        try:
            # Extract agent name from record.name or log category
            agent = "SYSTEM"
            name = record.name.lower()
            if "zone_finder" in name or "zone_finders_code" in name or "swarm" in name:
                agent = "Agent 3 — Commercial Zone Discovery"
            elif "city_segment" in name:
                agent = "Agent 2 — City Discovery"
            elif "company_finder" in name or "main" in name:
                agent = "Agent 4 — Sub-Area Mapping"
            elif "execution" in name or "scraper" in name or "playwright" in name:
                agent = "Agent 5 — Lead Scraping"
                
            level = record.levelname
            msg = record.getMessage()
            self.orchestrator._log(agent, level, msg)
        finally:
            self._local.emitting = False


# ═══════════════════════════════════════════════════════════════════════════
#  Production Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class PipelineOrchestrator:
    """
    Single-instance production orchestrator.

    Usage:
        orch = PipelineOrchestrator()
        orch.start(top_n=5)          # non-blocking — runs in background thread
        orch.stop()                   # graceful shutdown
        orch.metrics                  # live PipelineMetrics
        orch.log_bus                  # LogBus for SSE streaming
    """

    def __init__(self):
        self.log_bus = LogBus()
        self.metrics: Optional[PipelineMetrics] = None
        self._state: Optional[PipelineState] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._metric_thread: Optional[threading.Thread] = None

    # ── Public API ──────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        top_n: Optional[int] = None,
        selected_countries: Optional[List[str]] = None,
        selected_cities: Optional[List[str]] = None,
        selected_zones: Optional[List[str]] = None,
        max_scrolls: int = 8,
        max_scrapers: int = 3,
        skip_supabase: bool = False,
    ) -> None:
        with self._lock:
            if self.is_running():
                raise RuntimeError("Pipeline is already running.")
            self._stop_event.clear()
            pipeline_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.metrics = PipelineMetrics(pipeline_id=pipeline_id)
            self._state = PipelineState()
            self._state.on_failure_callback = self._on_state_failure
            self._state.orchestrator = self  # Link orchestrator for active instance reporting
            self._thread = threading.Thread(
                target=self._run,
                args=(top_n, selected_countries or [], selected_cities or [],
                      selected_zones or [], max_scrolls, max_scrapers, skip_supabase),
                daemon=True,
            )
            self._thread.start()
            self._start_metric_monitor()

    def stop(self) -> None:
        self._stop_event.set()
        self._log("SYSTEM", "INFO", "Stop signal received — shutting down gracefully…")
        # Explicitly and safely reset all live instance counters to prevent "phantom" workers
        # from lingering on the UI if threads don't reach their finally block in time.
        if self.metrics:
            for agent in self.metrics.agents.values():
                agent.reset_active_instances()

    def get_status(self) -> Dict:
        m = self.metrics
        if m is None:
            return {"status": "idle", "agents": {}, "counts": {}}
        return {
            "status": m.status,
            "pipeline_id": m.pipeline_id,
            "elapsed": m.elapsed,
            "agents": {k: v.to_dict() for k, v in m.agents.items()},
            "counts": {
                "countries": m.countries,
                "cities": m.cities,
                "zones": m.zones,
                "subareas": m.subareas,
                "companies_raw": m.companies_raw,
                "companies": m.companies_deduped,
                "duplicates_removed": m.duplicates_removed,
                "supabase_inserted": m.supabase_inserted,
            },
            "system": {
                "peak_cpu": m.peak_cpu,
                "peak_mem_mb": round(m.peak_mem_mb, 1),
                "cpu_now": psutil.cpu_percent(interval=None),
                "mem_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 1),
            },
            "output_file": m.output_file,
            "error": m.error,
            "failed_agent": m.failed_agent,
        }

    # ── Internal helpers ────────────────────────────────────────────────

    def _categorize_error(self, err_msg: str, tb_msg: str = "") -> str:
        combined = f"{err_msg} {tb_msg}".lower()
        
        # 1. Supabase rate limits or connection/db problems
        if any(kw in combined for kw in ["supabase", "postgrest", "postgres", "database", "db_err", "db_connection"]):
            if any(rl_kw in combined for rl_kw in ["rate limit", "429", "too many requests"]):
                return "Supabase rate limit exceeded"
            return "Supabase connection/database problem"
            
        # 2. LLMs Rate Limits / Tokens exhausted
        if any(kw in combined for kw in ["groq", "gemini", "openai", "claude", "llm", "llama", "chat completion"]):
            if any(rl_kw in combined for rl_kw in ["429", "rate limit", "too many requests", "token", "tpm", "rpm", "exhausted", "quota", "limit exceeded"]):
                return "LLMs tokens has exhausted or rate limit exceeded"
            return "LLM service failure"
            
        # 3. Tavily Search
        if "tavily" in combined:
            if any(rl_kw in combined for rl_kw in ["429", "rate limit", "too many requests", "432"]):
                return "Tavily search rate limit exceeded"
            return "Tavily search service failure"
            
        # 4. General Rate limits / Token exhaustion
        if any(rl_kw in combined for rl_kw in ["rate limit", "429", "too many requests"]):
            return "API rate limit exceeded"
        if any(tok_kw in combined for tok_kw in ["token", "exhausted", "quota"]):
            return "Tokens / quota has exhausted"
            
        return "General execution error"

    def _on_state_failure(self, phase_name: str, failure_dict: dict) -> None:
        err_msg = failure_dict.get("error", "")
        tb_msg = failure_dict.get("traceback", "")
        cause = self._categorize_error(err_msg, tb_msg)
        inst = failure_dict.get("instance_id", "Unknown")
        self._log(phase_name, "ERROR", f"  ✗ Failure on {inst} due to: {cause}")
        self._log(phase_name, "ERROR", f"    Details: {err_msg}")

    def _log(self, agent: str, level: str, message: str) -> None:
        entry = LogEntry(
            ts=datetime.now().strftime("%H:%M:%S"),
            level=level,
            agent=agent,
            message=message,
        )
        self.log_bus.emit(entry)
        # Mirror to Python logging — wrapped to prevent UnicodeEncodeError on
        # Windows CP1252 consoles from propagating as a pipeline exception.
        try:
            py_level = {
                "ERROR": logging.ERROR, "WARN": logging.WARNING,
            }.get(level, logging.INFO)
            safe_msg = f"[{agent}] {message}"
            # Encode/decode to replace unmappable chars before handing to the handler
            safe_msg = safe_msg.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            
            # Temporarily disable LogBusHandler interception for our own mirrored logs
            if hasattr(self, '_log_handler'):
                self._log_handler._local.emitting = True
            try:
                logging.log(py_level, safe_msg)
            finally:
                if hasattr(self, '_log_handler'):
                    self._log_handler._local.emitting = False
        except Exception:
            pass  # Never let a log mirroring error crash the pipeline

    def _divider(self, agent: str, char: str = "=", width: int = 50) -> None:
        self._log(agent, "STAGE", char * width)

    def _check_stop(self) -> bool:
        if self._stop_event.is_set():
            self._log("SYSTEM", "WARN", "Pipeline stopped by user request.")
            if self.metrics:
                self.metrics.status = "stopped"
            return True
        return False

    def _start_agent(self, agent_id: str, name: str) -> AgentMetrics:
        m = AgentMetrics(agent_id=agent_id, agent_name=name, status="running",
                         start_time=time.time())
        if self.metrics:
            self.metrics.agents[agent_id] = m
        self._divider(name)
        self._log(name, "STAGE", f"Agent {agent_id} — {name}")
        self._divider(name, "─")
        return m

    def _finish_agent(self, m: AgentMetrics, success: bool, output_count: int = 0,
                      items_out: Optional[List[str]] = None) -> None:
        m.end_time = time.time()
        m.output_count = output_count
        m.items_out = items_out or []
        m.status = "done" if success else "failed"
        icon = "✓" if success else "✗"
        self._log(m.agent_name, "SUCCESS" if success else "ERROR",
                  f"{icon} {m.agent_name} — {m.output_count} records — {m.elapsed}")

    def _validate_api_keys(self) -> bool:
        """Check all required API keys are present."""
        self._log("SYSTEM", "INFO", "Validating API keys…")
        required = {
            "GROQ_API_KEY": "Groq LLM",
            "TAVILY_API_KEY": "Tavily Search",
        }
        optional = {
            "SUPABASE_URL": "Supabase",
            "SUPABASE_KEY": "Supabase",
        }
        all_ok = True
        for key, name in required.items():
            val = os.getenv(key)
            if val:
                self._log("SYSTEM", "SUCCESS", f"  ✓ {name} key found")
            else:
                self._log("SYSTEM", "ERROR", f"  ✗ {name} key MISSING ({key})")
                all_ok = False

        for key, name in optional.items():
            val = os.getenv(key)
            status = "✓" if val else "⚠ (optional)"
            self._log("SYSTEM", "INFO", f"  {status} {name} ({key})")

        return all_ok

    def _save_checkpoint(self) -> None:
        if self._state is None or self.metrics is None:
            return
        try:
            cp = {
                "pipeline_id": self.metrics.pipeline_id,
                "saved_at": datetime.now().isoformat(),
                "countries": self._state.gdp_ranked_countries,
                "cities": self._state.all_cities,
                "zone_registry": {
                    f"{k[0]}|{k[1]}": v
                    for k, v in self._state.master_zone_registry.items()
                },
                "subarea_rows": self._state.all_subarea_rows,
                "companies": self._state.scraped_companies,
                "metrics": self.metrics.to_dict(),
            }
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(cp, f, indent=2, ensure_ascii=False)
            self._log("SYSTEM", "INFO", f"  ✓ Checkpoint saved → {CHECKPOINT_FILE}")
        except Exception as e:
            self._log("SYSTEM", "WARN", f"  ⚠ Checkpoint save failed: {e}")

    def _generate_report(self) -> str:
        """Generate a structured JSON execution report."""
        if self.metrics is None:
            return ""
        os.makedirs(REPORT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(REPORT_DIR, f"pipeline_report_{ts}.json")
        report = {
            "pipeline_id": self.metrics.pipeline_id,
            "generated_at": datetime.now().isoformat(),
            "status": self.metrics.status,
            "elapsed": self.metrics.elapsed,
            "summary": {
                "countries": self.metrics.countries,
                "cities": self.metrics.cities,
                "zones": self.metrics.zones,
                "subareas": self.metrics.subareas,
                "companies_scraped": self.metrics.companies_raw,
                "companies_after_dedup": self.metrics.companies_deduped,
                "duplicates_removed": self.metrics.duplicates_removed,
                "supabase_inserted": self.metrics.supabase_inserted,
            },
            "agents": {k: v.to_dict() for k, v in self.metrics.agents.items()},
            "system": {
                "peak_cpu_pct": self.metrics.peak_cpu,
                "peak_mem_mb": round(self.metrics.peak_mem_mb, 1),
            },
            "output_file": self.metrics.output_file,
            "error": self.metrics.error,
            "logs": self.log_bus.history(),
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report_path

    def _start_metric_monitor(self) -> None:
        """Background thread that samples CPU/memory every 5 seconds."""
        def _monitor():
            proc = psutil.Process()
            while self.is_running():
                if self.metrics:
                    cpu = psutil.cpu_percent(interval=1)
                    mem = proc.memory_info().rss / 1024 / 1024
                    self.metrics.peak_cpu = max(self.metrics.peak_cpu, cpu)
                    self.metrics.peak_mem_mb = max(self.metrics.peak_mem_mb, mem)
                time.sleep(4)
        self._metric_thread = threading.Thread(target=_monitor, daemon=True)
        self._metric_thread.start()

    # ── Main execution ──────────────────────────────────────────────────

    def _run(
        self,
        top_n: Optional[int],
        selected_countries: List[str],
        selected_cities: List[str],
        selected_zones: List[str],
        max_scrolls: int,
        max_scrapers: int,
        skip_supabase: bool,
    ) -> None:
        m = self.metrics
        state = self._state
        assert m is not None and state is not None

        try:
            m.status = "running"
            # Register LogBusHandler to intercept all python logging from agents
            self._log_handler = LogBusHandler(self)
            logging.getLogger().addHandler(self._log_handler)

            # ── System Init ───────────────────────────────────────────
            self._divider("SYSTEM", "═")
            self._log("SYSTEM", "STAGE", "  OXIQ AI — PIPELINE INITIALIZING")
            self._divider("SYSTEM", "═")
            self._log("SYSTEM", "INFO", f"  Pipeline ID  : {m.pipeline_id}")
            self._log("SYSTEM", "INFO", f"  Started at   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("SYSTEM", "INFO", f"  Top-N filter : {top_n or 'ALL'}")
            self._log("SYSTEM", "INFO", f"  Skip Supabase: {skip_supabase}")

            if not self._validate_api_keys():
                raise RuntimeError("Required API keys are missing. Check your .env files.")

            self._log("SYSTEM", "SUCCESS", "✓ Configuration Loaded")
            self._log("SYSTEM", "SUCCESS", "✓ API Keys Verified")

            # ── Supabase connectivity check ────────────────────────────
            supa_url = os.getenv("SUPABASE_URL")
            supa_key = os.getenv("SUPABASE_KEY")
            if supa_url and supa_key and not skip_supabase:
                try:
                    from supabase import create_client
                    _sb = create_client(supa_url, supa_key)
                    self._log("SYSTEM", "SUCCESS", "✓ Database Connected (Supabase)")
                except Exception as e:
                    self._log("SYSTEM", "WARN", f"  ⚠ Supabase connection issue: {e}")
            else:
                self._log("SYSTEM", "INFO", "  ℹ Supabase skipped (no keys / skip_supabase=True)")

            if self._check_stop(): return

            # ══════════════════════════════════════════════════════════
            #  AGENT 1 — Country Discovery
            # ══════════════════════════════════════════════════════════
            am1 = self._start_agent("1", "Agent 1 — Country Discovery")
            self._log("Agent 1 — Country Discovery", "INFO", "  Loading GDP data…")
            try:
                args = Namespace(
                    countries=None, top_n=top_n, refresh_gdp=False,
                    cities=None, zones=None, max_scrolls=max_scrolls,
                    max_scrapers=max_scrapers, skip_supabase=skip_supabase,
                )
                phase_1_gdp_ranking(state, args)
                countries_list = state.gdp_ranked_countries

                if selected_countries:
                    countries_list = [c for c in countries_list
                                     if c.get("country_name") in selected_countries]
                    state.gdp_ranked_countries = countries_list

                m.countries = len(countries_list)
                am1.input_count = 1
                am1.items_out = [c.get("country_name", "") for c in countries_list]

                for c in countries_list:
                    self._log("Agent 1 — Country Discovery", "INFO",
                              f"  ✓ {c.get('country_name')} (GDP Rank #{c.get('gdp_rank', '?')})")

                self._log("Agent 1 — Country Discovery", "METRIC",
                          f"  Countries Found: {m.countries}")
                self._finish_agent(am1, True, m.countries, am1.items_out)
                self._save_checkpoint()

            except Exception as e:
                cause = self._categorize_error(str(e), traceback.format_exc())
                self._log("Agent 1 — Country Discovery", "ERROR", f"  ✗ CRITICAL FAILURE CAUSE: {cause}")
                self._log("Agent 1 — Country Discovery", "ERROR", f"    Details: {e}")
                am1.errors.append(f"{cause}: {e}")
                self._finish_agent(am1, False)
                raise RuntimeError(f"Agent 1 failed: {cause} (Details: {e})") from e

            if self._check_stop(): return
            if not state.gdp_ranked_countries:
                raise RuntimeError("Agent 1 produced 0 countries — cannot continue.")

            # ══════════════════════════════════════════════════════════
            #  AGENT 2 — City Discovery
            # ══════════════════════════════════════════════════════════
            am2 = self._start_agent("2", "Agent 2 — City Discovery")
            country_names = [c.get("country_name") for c in state.gdp_ranked_countries]
            self._log("Agent 2 — City Discovery", "INFO",
                      f"  Processing {len(country_names)} countries: {', '.join(str(x) for x in country_names)}")
            try:
                phase_2_city_segmentation(state, stop_event=self._stop_event)
                m.cities = len(state.all_cities)
                am2.input_count = len(country_names)
                am2.items_out = [c.get("city", "") for c in state.all_cities]

                # Print per-country breakdown
                countries_seen = {}
                for city in state.all_cities:
                    co = city.get("country", "?")
                    countries_seen.setdefault(co, []).append(city.get("city", "?"))
                for co, cities in countries_seen.items():
                    self._log("Agent 2 — City Discovery", "INFO", f"  {co}:")
                    for ci in cities[:8]:
                        self._log("Agent 2 — City Discovery", "INFO", f"    ✓ {ci}")
                    if len(cities) > 8:
                        self._log("Agent 2 — City Discovery", "INFO",
                                  f"    … and {len(cities)-8} more")

                self._log("Agent 2 — City Discovery", "METRIC",
                          f"  Cities Found: {m.cities}")
                self._finish_agent(am2, True, m.cities)
                self._save_checkpoint()

            except Exception as e:
                cause = self._categorize_error(str(e), traceback.format_exc())
                self._log("Agent 2 — City Discovery", "ERROR", f"  ✗ CRITICAL FAILURE CAUSE: {cause}")
                self._log("Agent 2 — City Discovery", "ERROR", f"    Details: {e}")
                am2.errors.append(f"{cause}: {e}")
                self._finish_agent(am2, False)
                raise RuntimeError(f"Agent 2 failed: {cause} (Details: {e})") from e

            if self._check_stop(): return
            if not state.all_cities:
                raise RuntimeError("Agent 2 produced 0 cities — cannot continue.")

            # ══════════════════════════════════════════════════════════
            #  AGENT 3 — Commercial Zone Discovery
            # ══════════════════════════════════════════════════════════
            am3 = self._start_agent("3", "Agent 3 — Commercial Zone Discovery")
            if selected_cities:
                state.all_cities = [c for c in state.all_cities
                                    if c.get("city") in selected_cities]
            self._log("Agent 3 — Commercial Zone Discovery", "INFO",
                      f"  Discovering zones for {len(state.all_cities)} cities…")
            try:
                phase_3_zone_finding(state, stop_event=self._stop_event)
                total_zones = sum(len(z) for z in state.master_zone_registry.values())
                m.zones = total_zones
                am3.input_count = len(state.all_cities)

                for (city, country), zones in state.master_zone_registry.items():
                    self._log("Agent 3 — Commercial Zone Discovery", "INFO",
                              f"  {city}, {country} → {len(zones)} zones:")
                    for z in zones[:5]:
                        self._log("Agent 3 — Commercial Zone Discovery", "INFO",
                                  f"    ✓ {z}")
                    if len(zones) > 5:
                        self._log("Agent 3 — Commercial Zone Discovery", "INFO",
                                  f"    … and {len(zones)-5} more")

                self._log("Agent 3 — Commercial Zone Discovery", "METRIC",
                          f"  Commercial Areas Found: {m.zones}")
                self._finish_agent(am3, True, m.zones)
                self._save_checkpoint()

            except Exception as e:
                cause = self._categorize_error(str(e), traceback.format_exc())
                self._log("Agent 3 — Commercial Zone Discovery", "ERROR", f"  ✗ CRITICAL FAILURE CAUSE: {cause}")
                self._log("Agent 3 — Commercial Zone Discovery", "ERROR", f"    Details: {e}")
                am3.errors.append(f"{cause}: {e}")
                self._finish_agent(am3, False)
                raise RuntimeError(f"Agent 3 failed: {cause} (Details: {e})") from e

            if self._check_stop(): return
            if not state.master_zone_registry:
                raise RuntimeError("Agent 3 produced 0 zones — cannot continue.")

            # ══════════════════════════════════════════════════════════
            #  AGENT 4 — Sub-Area Mapping
            # ══════════════════════════════════════════════════════════
            am4 = self._start_agent("4", "Agent 4 — Sub-Area Mapping")
            if selected_zones:
                orig = state.master_zone_registry
                state.master_zone_registry = {
                    (city, co): [z for z in zones if z in selected_zones]
                    for (city, co), zones in orig.items()
                    if any(z in selected_zones for z in zones)
                }
            zone_count = sum(len(z) for z in state.master_zone_registry.values())
            self._log("Agent 4 — Sub-Area Mapping", "INFO",
                      f"  Mapping sub-areas for {zone_count} zones…")
            try:
                phase_4_subarea_mapper(state, stop_event=self._stop_event)
                m.subareas = len(state.all_subarea_rows)
                am4.input_count = zone_count

                for row in state.all_subarea_rows[:6]:
                    self._log("Agent 4 — Sub-Area Mapping", "INFO",
                              f"  ✓ {row.get('subarea_name')} ({row.get('zone_name')})")
                if len(state.all_subarea_rows) > 6:
                    self._log("Agent 4 — Sub-Area Mapping", "INFO",
                              f"  … and {len(state.all_subarea_rows)-6} more")

                self._log("Agent 4 — Sub-Area Mapping", "METRIC",
                          f"  Sub-Areas Found: {m.subareas}")
                self._finish_agent(am4, True, m.subareas)

                # Phase 4.5 — Supabase insert (subareas)
                if not skip_supabase:
                    self._log("Agent 4 — Sub-Area Mapping", "INFO",
                              "  Inserting sub-areas into Supabase…")
                    try:
                        phase_4_5_supabase_insert(state, skip_supabase=False)
                        self._log("Agent 4 — Sub-Area Mapping", "SUCCESS",
                                  f"  ✓ {m.subareas} sub-areas inserted into Supabase")
                    except Exception as sb_err:
                        self._log("Agent 4 — Sub-Area Mapping", "WARN",
                                  f"  ⚠ Supabase insert partial/failed: {sb_err}")
                self._save_checkpoint()

            except Exception as e:
                cause = self._categorize_error(str(e), traceback.format_exc())
                self._log("Agent 4 — Sub-Area Mapping", "ERROR", f"  ✗ CRITICAL FAILURE CAUSE: {cause}")
                self._log("Agent 4 — Sub-Area Mapping", "ERROR", f"    Details: {e}")
                am4.errors.append(f"{cause}: {e}")
                self._finish_agent(am4, False)
                raise RuntimeError(f"Agent 4 failed: {cause} (Details: {e})") from e

            if self._check_stop(): return

            # ══════════════════════════════════════════════════════════
            #  EXECUTION ENGINE — Company Discovery (Playwright scraper)
            # ══════════════════════════════════════════════════════════
            am5 = self._start_agent("5", "Execution Engine — Company Discovery")
            self._log("Execution Engine — Company Discovery", "INFO",
                      f"  Scraping companies from {m.subareas} sub-areas…")
            self._log("Execution Engine — Company Discovery", "INFO",
                      f"  Max scrolls: {max_scrolls} | Max scrapers: {max_scrapers}")
            try:
                phase_5_lead_scraper(state, max_scrolls, max_scrapers, stop_event=self._stop_event)
                raw_count = len(state.scraped_companies)
                m.companies_raw = raw_count
                m.companies_deduped = raw_count   # already deduped inside phase_5
                am5.input_count = m.subareas

                for comp in state.scraped_companies[:8]:
                    self._log("Execution Engine — Company Discovery", "INFO",
                              f"  ✓ {comp.get('company_name')} ({comp.get('category', 'n/a')})")
                if raw_count > 8:
                    self._log("Execution Engine — Company Discovery", "INFO",
                              f"  … and {raw_count - 8} more")

                self._log("Execution Engine — Company Discovery", "METRIC",
                          f"  Companies Found: {raw_count}")
                self._finish_agent(am5, True, raw_count)

            except Exception as e:
                cause = self._categorize_error(str(e), traceback.format_exc())
                self._log("Execution Engine — Company Discovery", "ERROR", f"  ✗ CRITICAL FAILURE CAUSE: {cause}")
                self._log("Execution Engine — Company Discovery", "ERROR", f"    Details: {e}")
                am5.errors.append(f"{cause}: {e}")
                self._finish_agent(am5, False)
                raise RuntimeError(f"Execution Engine failed: {cause} (Details: {e})") from e

            if self._check_stop(): return

            # ══════════════════════════════════════════════════════════
            #  VALIDATION — Deduplication & integrity check
            # ══════════════════════════════════════════════════════════
            self._divider("Validation")
            self._log("Validation", "STAGE", "Validation — Data Integrity")
            self._divider("Validation", "─")

            companies = state.scraped_companies
            # Count invalid (missing company_name)
            valid = [c for c in companies if c.get("company_name", "").strip()]
            invalid_count = len(companies) - len(valid)
            m.invalid_records = invalid_count
            m.companies_deduped = len(valid)

            self._log("Validation", "INFO",
                      f"  Companies Raw       : {len(companies)}")
            self._log("Validation", "INFO",
                      f"  Invalid Records     : {invalid_count}")
            self._log("Validation", "SUCCESS",
                      f"  Valid Companies     : {len(valid)}")

            state.scraped_companies = valid

            # ══════════════════════════════════════════════════════════
            #  SAVE RESULTS
            # ══════════════════════════════════════════════════════════
            self._divider("Output")
            self._log("Output", "STAGE", "Saving Data…")
            self._divider("Output", "─")

            os.makedirs(REPORT_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(REPORT_DIR, f"pipeline_lead_results_{ts}.json")

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(state.scraped_companies, f, indent=2, ensure_ascii=False)
            m.output_file = out_file
            self._log("Output", "SUCCESS", f"  ✓ JSON Saved → {out_file}")
            self._log("Output", "INFO",
                      f"  Total records written: {len(state.scraped_companies)}")

            # Supabase insert (leads)
            if not skip_supabase and state.scraped_companies:
                self._log("Output", "INFO",
                          f"  Inserting {len(state.scraped_companies)} leads into Supabase…")
                try:
                    phase_5_5_supabase_insert_leads(state, skip_supabase=False)
                    m.supabase_inserted = len(state.scraped_companies)
                    self._log("Output", "SUCCESS",
                              f"  ✓ Database Updated — {m.supabase_inserted} rows inserted")
                except Exception as sb_err:
                    self._log("Output", "WARN",
                              f"  ⚠ Supabase insert partial/failed: {sb_err}")

            # ══════════════════════════════════════════════════════════
            #  REPORT
            # ══════════════════════════════════════════════════════════
            state.finalize()
            m.end_time = time.time()
            m.status = "done"

            report_path = self._generate_report()
            if report_path:
                self._log("Output", "SUCCESS", f"  ✓ Report Generated → {report_path}")

            # ── Final Summary ─────────────────────────────────────────
            self._divider("SUMMARY", "═")
            self._log("SUMMARY", "STAGE", "  PIPELINE SUMMARY")
            self._divider("SUMMARY", "═")
            self._log("SUMMARY", "INFO", f"  Countries         : {m.countries}")
            self._log("SUMMARY", "INFO", f"  Cities            : {m.cities}")
            self._log("SUMMARY", "INFO", f"  Commercial Areas  : {m.zones}")
            self._log("SUMMARY", "INFO", f"  Sub-Areas         : {m.subareas}")
            self._log("SUMMARY", "INFO", f"  Companies Scraped : {m.companies_raw}")
            self._log("SUMMARY", "INFO", f"  After Dedup       : {m.companies_deduped}")
            self._log("SUMMARY", "INFO", f"  Supabase Inserted : {m.supabase_inserted}")
            self._log("SUMMARY", "INFO", f"  Execution Time    : {m.elapsed}")
            self._log("SUMMARY", "INFO", f"  Peak CPU          : {m.peak_cpu:.1f}%")
            self._log("SUMMARY", "INFO", f"  Peak Memory       : {m.peak_mem_mb:.0f} MB")
            self._divider("SUMMARY", "═")
            self._log("SUMMARY", "SUCCESS", "  Status: SUCCESS ✓")
            self._divider("SUMMARY", "═")

        except Exception as e:
            tb = traceback.format_exc()
            cause = self._categorize_error(str(e), tb)
            if self.metrics:
                self.metrics.status = "failed"
                self.metrics.error = f"{cause} (Details: {e})"
                self.metrics.end_time = time.time()
                # find which agent failed
                for aid, am in self.metrics.agents.items():
                    if am.status == "running":
                        am.status = "failed"
                        am.end_time = time.time()
                        self.metrics.failed_agent = am.agent_name
                        break

            self._divider("SYSTEM", "!")
            self._log("SYSTEM", "ERROR", f"  PIPELINE FAILED: {cause}")
            self._log("SYSTEM", "ERROR", f"  Details: {e}")
            self._log("SYSTEM", "ERROR", f"  Traceback:\n{tb}")
            self._divider("SYSTEM", "!")

            # Save checkpoint even on failure so user can resume
            self._save_checkpoint()
        finally:
            if hasattr(self, '_log_handler'):
                logging.getLogger().removeHandler(self._log_handler)
