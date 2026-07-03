# """
# ui_app.py — Streamlit UI for the Master Agent Pipeline
# =======================================================
# Visualizes each phase of the autonomous parallel orchestrator with
# live logs, phase status cards, and interactive result tables.

# Run with:
#     streamlit run ui_app.py
# """

# import os
# import sys
# import json
# import time
# import queue
# import threading
# import argparse
# import importlib
# from datetime import datetime
# from contextlib import redirect_stdout

# import streamlit as st

# # ─────────────────────────────────────────────────────────────────────
# # Path setup (mirrors run_pipeline.py)
# # ─────────────────────────────────────────────────────────────────────
# project_root = os.path.dirname(os.path.abspath(__file__))
# if os.path.basename(project_root).lower().replace(" ", "_") in ("master_agent", "master agent"):
#     project_root = os.path.dirname(project_root)

# sub1_path = os.path.join(project_root, "SUB AGENT 1", "SUB AGENT 1 gdp ranker")
# sub2_path = os.path.join(project_root, "SUB AGENT 2")
# sub3_path = os.path.join(project_root, "SUB AGENT 3 zone finder")
# sub4_path = os.path.join(project_root, "SUB_AGENT 4 sub area mapper")
# exec_path = os.path.join(project_root, "execution_engine")

# for p in [sub1_path, sub2_path, sub3_path, sub4_path, exec_path, project_root]:
#     if p and os.path.exists(p) and p not in sys.path:
#         sys.path.append(p)

# from dotenv import load_dotenv
# load_dotenv(os.path.join(project_root, ".env"))
# os.environ.pop("NVIDIA_API_KEY", None)
# os.environ.pop("OPEN_ROUTER_AI_KEY", None)

# # Import the pipeline module and its dependencies
# import run_pipeline
# from orchestrator_utils import PipelineState


# # ─────────────────────────────────────────────────────────────────────
# # Session state initialization
# # ─────────────────────────────────────────────────────────────────────
# def init_session_state():
#     defaults = {
#         "running": False,
#         "done": False,
#         "error": None,
#         "phase_status": {
#             "phase_1":   "pending",   # GDP Ranking
#             "phase_2":   "pending",   # City Segmentation
#             "phase_3":   "pending",   # Zone Finding
#             "phase_4":   "pending",   # Sub-Area Mapping
#             "phase_4_5": "pending",   # Supabase insert (subareas)
#             "phase_5":   "pending",   # Lead Scraper
#             "phase_5_5": "pending",   # Supabase insert (leads)
#         },
#         "logs": [],
#         "log_queue": queue.Queue(),
#         "pipeline_state": None,
#         "output_file": None,
#         "start_time": None,
#         "end_time": None,
#     }
#     for k, v in defaults.items():
#         if k not in st.session_state:
#             st.session_state[k] = v


# # ─────────────────────────────────────────────────────────────────────
# # Log capture: redirects stdout into a queue
# # ─────────────────────────────────────────────────────────────────────
# class QueueWriter:
#     """File-like object that pushes lines into a queue."""
#     def __init__(self, q):
#         self.q = q
#         self._buf = ""

#     def write(self, text):
#         self._buf += text
#         while "\n" in self._buf:
#             line, self._buf = self._buf.split("\n", 1)
#             if line.strip():
#                 self.q.put(line)

#     def flush(self):
#         if self._buf.strip():
#             self.q.put(self._buf)
#             self._buf = ""


# # ─────────────────────────────────────────────────────────────────────
# # Phase definitions for UI rendering
# # ─────────────────────────────────────────────────────────────────────
# PHASES = [
#     {"key": "phase_1",   "num": 1,     "name": "GDP Ranking",            "agent": "Agent 1",      "icon": "🌍", "desc": "Ranks countries by GDP (sequential, single instance)"},
#     {"key": "phase_2",   "num": 2,     "name": "City Segmentation",      "agent": "Agent 2",      "icon": "🏙️", "desc": "Segments countries into tier-1/2/3 cities (parallel)"},
#     {"key": "phase_3",   "num": 3,     "name": "Zone Finding",           "agent": "Agent 3",      "icon": "📍", "desc": "Finds zones within each city (parallel)"},
#     {"key": "phase_4",   "num": 4,     "name": "Sub-Area Mapping",       "agent": "Agent 5",      "icon": "🗺️", "desc": "Maps sub-areas within each zone (hyper-parallel)"},
#     {"key": "phase_4_5", "num": "4.5", "name": "Supabase Insert",        "agent": "Database",     "icon": "💾", "desc": "Inserts sub-areas into Supabase (optional)"},
#     {"key": "phase_5",   "num": 5,     "name": "Lead Scraping",          "agent": "Agent 6",      "icon": "🔍", "desc": "Playwright scraper for business leads (hyper-parallel)"},
#     {"key": "phase_5_5", "num": "5.5", "name": "Leads Supabase Insert",  "agent": "Database",     "icon": "📤", "desc": "Inserts scraped leads into Supabase (optional)"},
# ]

# STATUS_STYLE = {
#     "pending": ("⚪", "secondary"),
#     "running": ("🔵", "primary"),
#     "done":    ("✅", "success"),
#     "failed":  ("❌", "error"),
#     "skipped": ("⏭️", "warning"),
# }


# # ─────────────────────────────────────────────────────────────────────
# # Pipeline execution in a background thread
# # ─────────────────────────────────────────────────────────────────────
# def set_phase(key, status):
#     st.session_state.phase_status[key] = status


# def pipeline_worker(args_dict):
#     """Runs the full pipeline in a background thread with stdout capture."""
#     q = st.session_state.log_queue
#     old_stdout = sys.stdout
#     sys.stdout = QueueWriter(q)

#     try:
#         args = argparse.Namespace(**args_dict)
#         state = PipelineState()
#         st.session_state.pipeline_state = state

#         q.put("=" * 60)
#         q.put("MASTER AGENT AUTONOMOUS PARALLEL ORCHESTRATOR")
#         q.put("=" * 60)

#         # ── Direct Zone Mode ──
#         if args.zones:
#             set_phase("phase_1", "skipped")
#             set_phase("phase_2", "skipped")
#             set_phase("phase_3", "skipped")
#             direct_zones = [z.strip() for z in args.zones.split(",") if z.strip()]
#             city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
#             country = args.countries.split(",")[0].strip() if args.countries else "India"
#             state.master_zone_registry[(city, country)] = direct_zones
#             state.all_cities.append({"city": city, "country": country, "tier": 1})
#             q.put(f"Direct Zone Mode: {len(direct_zones)} zones in {city}, {country}")

#         # ── Direct City Mode ──
#         elif args.cities:
#             set_phase("phase_1", "skipped")
#             set_phase("phase_2", "skipped")
#             cities = [c.strip() for c in args.cities.split(",") if c.strip()]
#             country = args.countries.split(",")[0].strip() if args.countries else "India"
#             for cn in cities:
#                 state.all_cities.append({"city": cn, "country": country, "tier": 1})
#             q.put(f"Direct City Mode: {len(cities)} cities")
#             set_phase("phase_3", "running")
#             run_pipeline.phase_3_zone_finding(state)
#             set_phase("phase_3", "done")

#         # ── Full Pipeline ──
#         else:
#             set_phase("phase_1", "running")
#             run_pipeline.phase_1_gdp_ranking(state, args)
#             set_phase("phase_1", "done")

#             set_phase("phase_2", "running")
#             run_pipeline.phase_2_city_segmentation(state)
#             set_phase("phase_2", "done")

#             if not state.all_cities:
#                 q.put("[Error] No cities found after Phase 2. Stopping.")
#                 set_phase("phase_3", "skipped")
#                 raise RuntimeError("No cities after Phase 2")

#             set_phase("phase_3", "running")
#             run_pipeline.phase_3_zone_finding(state)
#             set_phase("phase_3", "done")

#         # ── Phase 4 ──
#         if not state.master_zone_registry:
#             q.put("[Error] No zones available. Stopping before Phase 4.")
#             for p in ["phase_4", "phase_4_5", "phase_5", "phase_5_5"]:
#                 set_phase(p, "skipped")
#             raise RuntimeError("No zones to process")

#         set_phase("phase_4", "running")
#         run_pipeline.phase_4_subarea_mapper(state)
#         set_phase("phase_4", "done")

#         # ── Phase 4.5 ──
#         set_phase("phase_4_5", "running")
#         run_pipeline.phase_4_5_supabase_insert(state, args.skip_supabase)
#         set_phase("phase_4_5", "done" if not args.skip_supabase else "skipped")

#         # ── Phase 5 ──
#         set_phase("phase_5", "running")
#         run_pipeline.phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers)
#         set_phase("phase_5", "done")

#         # ── Phase 5.5 ──
#         set_phase("phase_5_5", "running")
#         run_pipeline.phase_5_5_supabase_insert_leads(state, args.skip_supabase)
#         set_phase("phase_5_5", "done" if not args.skip_supabase else "skipped")

#         state.finalize()

#         # Save final output
#         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
#         out_dir = os.path.join(project_root, "outputs")
#         os.makedirs(out_dir, exist_ok=True)
#         out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
#         with open(out_file, "w", encoding="utf-8") as f:
#             json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
#         st.session_state.output_file = out_file

#         q.put("=" * 60)
#         q.put("PIPELINE COMPLETED SUCCESSFULLY")
#         q.put(f"Total Companies Scraped: {len(state.scraped_companies)}")
#         q.put(f"Output File: {out_file}")
#         q.put("=" * 60)

#     except Exception as e:
#         import traceback
#         q.put(f"[FATAL ERROR] {e}")
#         q.put(traceback.format_exc())
#         st.session_state.error = str(e)
#         # Mark any running phase as failed
#         for k, v in st.session_state.phase_status.items():
#             if v == "running":
#                 st.session_state.phase_status[k] = "failed"
#     finally:
#         sys.stdout = old_stdout
#         st.session_state.running = False
#         st.session_state.done = True
#         st.session_state.end_time = datetime.now()
#         q.put("__PIPELINE_DONE__")


# # ─────────────────────────────────────────────────────────────────────
# # UI components
# # ─────────────────────────────────────────────────────────────────────
# def render_sidebar():
#     with st.sidebar:
#         st.title("⚙️ Configuration")
#         st.caption("Master Agent Orchestrator")

#         mode = st.radio(
#             "Run Mode",
#             ["Full Pipeline", "Direct Cities", "Direct Zones"],
#             help="Full Pipeline runs GDP ranking → cities → zones → subareas → leads. "
#                  "Direct modes skip earlier phases."
#         )

#         args_dict = {
#             "countries": None,
#             "top_n": None,
#             "refresh_gdp": False,
#             "cities": None,
#             "zones": None,
#             "max_scrolls": 8,
#             "max_scrapers": 3,
#             "skip_supabase": False,
#         }

#         if mode == "Full Pipeline":
#             args_dict["countries"] = st.text_input(
#                 "Countries (comma-separated, optional — overrides GDP ranking)",
#                 placeholder="e.g. India,United States"
#             ).strip() or None
#             args_dict["top_n"] = st.number_input(
#                 "Top N countries from GDP_data.json (0 = all)", 0, 200, 0
#             ) or None
#             args_dict["refresh_gdp"] = st.checkbox("Refresh GDP ranking", False)
#         elif mode == "Direct Cities":
#             args_dict["cities"] = st.text_input(
#                 "Cities (comma-separated)", placeholder="e.g. Mumbai, Delhi, Bangalore"
#             ).strip()
#             args_dict["countries"] = st.text_input(
#                 "Country", value="India"
#             ).strip() or None
#         else:  # Direct Zones
#             args_dict["zones"] = st.text_input(
#                 "Zones (comma-separated)", placeholder="e.g. Andheri, Bandra, Powai"
#             ).strip()
#             args_dict["cities"] = st.text_input(
#                 "City", value="Mumbai"
#             ).strip()
#             args_dict["countries"] = st.text_input(
#                 "Country", value="India"
#             ).strip() or None

#         st.divider()
#         st.subheader("Scraper Settings")
#         args_dict["max_scrolls"] = st.slider("Max scrolls per sub-area", 1, 30, 8)
#         args_dict["max_scrapers"] = st.slider("Max concurrent browser instances", 1, 10, 3)
#         args_dict["skip_supabase"] = st.checkbox("Skip Supabase insertion", False)

#         st.divider()
#         start_disabled = st.session_state.running
#         if st.button("🚀 Start Pipeline", type="primary", disabled=start_disabled, use_container_width=True):
#             start_pipeline(args_dict)

#         if st.session_state.running:
#             st.warning("⏳ Pipeline running... please wait.")
#         elif st.session_state.done:
#             if st.button("🔄 Reset", use_container_width=True):
#                 reset_session()

#         st.divider()
#         st.caption(f"**Project root:**\n`{project_root}`")
#         return args_dict


# def start_pipeline(args_dict):
#     # Reset state
#     st.session_state.running = True
#     st.session_state.done = False
#     st.session_state.error = None
#     st.session_state.output_file = None
#     st.session_state.start_time = datetime.now()
#     st.session_state.end_time = None
#     st.session_state.logs = []
#     # Clear the queue
#     while not st.session_state.log_queue.empty():
#         try:
#             st.session_state.log_queue.get_nowait()
#         except queue.Empty:
#             break
#     for k in st.session_state.phase_status:
#         st.session_state.phase_status[k] = "pending"

#     thread = threading.Thread(target=pipeline_worker, args=(args_dict,), daemon=True)
#     thread.start()


# def reset_session():
#     st.session_state.running = False
#     st.session_state.done = False
#     st.session_state.error = None
#     st.session_state.pipeline_state = None
#     st.session_state.output_file = None
#     st.session_state.start_time = None
#     st.session_state.end_time = None
#     st.session_state.logs = []
#     for k in st.session_state.phase_status:
#         st.session_state.phase_status[k] = "pending"


# def render_phase_cards():
#     st.subheader("Pipeline Phases")
#     cols = st.columns(len(PHASES))
#     for col, phase in zip(cols, PHASES):
#         status = st.session_state.phase_status.get(phase["key"], "pending")
#         icon, badge = STATUS_STYLE.get(status, ("⚪", "secondary"))
#         with col:
#             st.markdown(
#                 f"""
#                 <div style="
#                     border: 1px solid rgba(128,128,128,0.2);
#                     border-radius: 10px;
#                     padding: 12px 8px;
#                     text-align: center;
#                     height: 170px;
#                     background: rgba(255,255,255,0.03);
#                 ">
#                     <div style="font-size: 26px;">{phase['icon']}</div>
#                     <div style="font-weight: 700; font-size: 13px; margin-top: 4px;">
#                         Phase {phase['num']}
#                     </div>
#                     <div style="font-size: 12px; color: #aaa; margin-top: 2px;">
#                         {phase['name']}
#                     </div>
#                     <div style="font-size: 10px; color: #888; margin-top: 4px;">
#                         {phase['agent']}
#                     </div>
#                     <div style="margin-top: 8px; font-size: 11px;">
#                         {icon} <b>{status.upper()}</b>
#                     </div>
#                 </div>
#                 """,
#                 unsafe_allow_html=True,
#             )


# def render_progress_bar():
#     statuses = list(st.session_state.phase_status.values())
#     done = sum(1 for s in statuses if s in ("done", "skipped"))
#     total = len(statuses)
#     pct = int(done / total * 100) if total else 0
#     st.progress(pct / 100, text=f"Overall progress: {pct}%  ({done}/{total} phases complete)")


# def render_logs():
#     st.subheader("📜 Live Logs")
#     log_box = st.container(height=320)
#     with log_box:
#         if not st.session_state.logs:
#             st.caption("No logs yet. Start the pipeline to see real-time output.")
#         else:
#             for line in st.session_state.logs[-500:]:  # last 500 lines
#                 # Color-code certain lines
#                 if line.strip().startswith("[ERROR") or "ERROR" in line or "FATAL" in line:
#                     st.error(line)
#                 elif line.strip().startswith("[OK]") or "completed" in line.lower() or "SUCCESS" in line:
#                     st.success(line)
#                 elif line.strip().startswith("[WARNING") or "WARNING" in line:
#                     st.warning(line)
#                 elif line.strip().startswith("-> Phase") or line.strip().startswith("=" * 10):
#                     st.markdown(f"**{line}**")
#                 else:
#                     st.text(line)


# def render_results():
#     state: PipelineState = st.session_state.pipeline_state
#     if not state:
#         return

#     st.subheader("📊 Phase Results")

#     # ── Phase 1: Countries ──
#     if state.gdp_ranked_countries:
#         with st.expander(f"🌍 Phase 1 — GDP Ranked Countries ({len(state.gdp_ranked_countries)})", expanded=False):
#             rows = []
#             for i, c in enumerate(state.gdp_ranked_countries, 1):
#                 if isinstance(c, dict):
#                     rows.append({"Rank": c.get("gdp_rank", i), "Country": c.get("country_name", "?")})
#                 else:
#                     rows.append({"Rank": i, "Country": c})
#             st.dataframe(rows, use_container_width=True, height=300)

#     # ── Phase 2: City Registry ──
#     if state.master_city_registry:
#         with st.expander(f"🏙️ Phase 2 — Master City Registry ({len(state.master_city_registry)} countries, {len(state.all_cities)} cities)", expanded=False):
#             rows = []
#             for c in state.all_cities:
#                 rows.append({
#                     "City": c["city"],
#                     "Country": c["country"],
#                     "Tier": c["tier"]
#                 })
#             st.dataframe(rows, use_container_width=True, height=300)

#     # ── Phase 3: Zone Registry ──
#     if state.master_zone_registry:
#         total_zones = sum(len(z) for z in state.master_zone_registry.values())
#         with st.expander(f"📍 Phase 3 — Master Zone Registry ({total_zones} zones)", expanded=False):
#             rows = []
#             for (city, country), zones in state.master_zone_registry.items():
#                 for z in zones:
#                     rows.append({"City": city, "Country": country, "Zone": z})
#             st.dataframe(rows, use_container_width=True, height=300)

#     # ── Phase 4: Sub-Areas ──
#     if state.all_subarea_rows:
#         with st.expander(f"🗺️ Phase 4 — Sub-Areas ({len(state.all_subarea_rows)} rows)", expanded=False):
#             st.dataframe(state.all_subarea_rows, use_container_width=True, height=400)

#     # ── Phase 5: Leads ──
#     if state.scraped_companies:
#         with st.expander(f"🔍 Phase 5 — Scraped Leads ({len(state.scraped_companies)} unique companies)", expanded=True):
#             st.dataframe(state.scraped_companies, use_container_width=True, height=500)

#             # Download button
#             if st.session_state.output_file and os.path.exists(st.session_state.output_file):
#                 with open(st.session_state.output_file, "rb") as f:
#                     st.download_button(
#                         "⬇️ Download leads JSON",
#                         f,
#                         file_name=os.path.basename(st.session_state.output_file),
#                         mime="application/json"
#                     )

#     # ── Failures ──
#     if state.failures:
#         with st.expander(f"⚠️ Dropped Slices / Failures ({len(state.failures)})", expanded=False):
#             for f in state.failures:
#                 st.error(f"**Phase:** {f.get('phase', '?')}  |  **Instance:** {f.get('instance_id', '?')}\n\nError: `{f.get('error', '?')}`")


# def render_summary_metrics():
#     state: PipelineState = st.session_state.pipeline_state
#     if not state:
#         return

#     c1, c2, c3, c4 = st.columns(4)
#     c1.metric("Countries", len(state.gdp_ranked_countries))
#     c2.metric("Cities", len(state.all_cities))
#     c3.metric("Zones", sum(len(z) for z in state.master_zone_registry.values()))
#     c4.metric("Sub-Areas", len(state.all_subarea_rows))

#     c5, c6, c7, c8 = st.columns(4)
#     c5.metric("Scraped Leads", len(state.scraped_companies))
#     c6.metric("Failures", len(state.failures))

#     if st.session_state.start_time and st.session_state.end_time:
#         duration = (st.session_state.end_time - st.session_state.start_time).total_seconds()
#         c7.metric("Duration", f"{duration:.1f}s")
#     elif st.session_state.start_time and st.session_state.running:
#         duration = (datetime.now() - st.session_state.start_time).total_seconds()
#         c7.metric("Elapsed", f"{duration:.1f}s")
#     if st.session_state.output_file:
#         c8.metric("Output File", os.path.basename(st.session_state.output_file))


# # ─────────────────────────────────────────────────────────────────────
# # Main
# # ─────────────────────────────────────────────────────────────────────
# def main():
#     st.set_page_config(
#         page_title="Master Agent Pipeline",
#         page_icon="🤖",
#         layout="wide",
#         initial_sidebar_state="expanded",
#     )
#     init_session_state()

#     st.title("🤖 Master Agent — Autonomous Parallel Orchestrator")
#     st.caption("GDP Ranking → City Segmentation → Zone Finding → Sub-Area Mapping → Lead Scraping")

#     render_sidebar()

#     # Drain the log queue into session_state.logs
#     drained = False
#     while True:
#         try:
#             line = st.session_state.log_queue.get_nowait()
#             if line == "__PIPELINE_DONE__":
#                 drained = True
#                 break
#             st.session_state.logs.append(line)
#         except queue.Empty:
#             break

#     render_progress_bar()
#     render_phase_cards()
#     st.divider()
#     render_summary_metrics()
#     st.divider()
#     render_logs()
#     st.divider()
#     render_results()

#     # Auto-refresh while pipeline is running
#     if st.session_state.running:
#         time.sleep(1.0)
#         st.rerun()


# if __name__ == "__main__":
#     main()

# -----------------------------------------------------------------------------


"""
ui_app.py — Streamlit Phase Dashboard for Master Agent Pipeline
"""

import streamlit as st
import threading
import queue
import time
import os
import sys
import json
from datetime import datetime
from argparse import Namespace

# ── Path setup ──────────────────────────────────────────────
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

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Sub-Area Mapper – Master Agent",
    page_icon="🗺️",
    layout="wide",
)

# ── Phase definitions ───────────────────────────────────────
PHASES = [
    {"num": 1,   "name": "GDP Ranking",         "icon": "🌍", "desc": "Load & rank countries by GDP"},
    {"num": 2,   "name": "City Segmentation",   "icon": "🏙️", "desc": "Identify tier-1/2/3 cities per country"},
    {"num": 3,   "name": "Zone Finding",        "icon": "📍", "desc": "Discover business zones per city"},
    {"num": 4,   "name": "Sub-Area Mapping",    "icon": "📐", "desc": "Map sub-areas within each zone"},
    {"num": 4.5, "name": "Supabase (Subareas)", "icon": "💾", "desc": "Insert subarea metadata into database"},
    {"num": 5,   "name": "Lead Scraping",       "icon": "🔍", "desc": "Scrape companies via Playwright"},
    {"num": 5.5, "name": "Supabase (Leads)",    "icon": "💾", "desc": "Insert scraped leads into database"},
]

# ── Session state init ──────────────────────────────────────
def _blank_phase():
    return {"status": "pending", "metrics": {}, "logs": [], "error": None}

if "phases" not in st.session_state:
    st.session_state.phases = {p["num"]: _blank_phase() for p in PHASES}
if "log_queue" not in st.session_state:
    st.session_state.log_queue = queue.Queue()
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False
if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
if "pipeline_error" not in st.session_state:
    st.session_state.pipeline_error = None
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

# ── Custom CSS ──────────────────────────────────────────────
st.markdown("""<style>
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
.phase-header{
    border-radius:10px;padding:14px 18px;margin-bottom:4px;
    transition:all .2s ease;
}
.ph-pending{background:#f9fafb;border:1px solid #e5e7eb;opacity:.5}
.ph-skipped{background:#fffbeb;border:1px dashed #fcd34d;opacity:.5}
.ph-running{background:#eff6ff;border:2px solid #93c5fd;box-shadow:0 0 12px #bfdbfe60}
.ph-done{background:#f0fdf4;border:1px solid #bbf7d0}
.ph-error{background:#fef2f2;border:2px solid #fca5a5}
.badge{
    display:inline-block;padding:5px 14px;border-radius:8px;
    font-size:13px;font-weight:600;letter-spacing:.2px;
}
.b-pending{background:#f3f4f6;color:#6b7280;border:1px solid #d1d5db}
.b-skipped{background:#fef3c7;color:#b45309;border:1px solid #fcd34d}
.b-running{background:#dbeafe;color:#1d4ed8;border:1px solid #93c5fd;animation:pulse 1.4s infinite}
.b-done{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.b-error{background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5}
.progress-track{background:#e5e7eb;border-radius:10px;height:10px;overflow:hidden}
.progress-fill{height:100%;border-radius:10px;transition:width .4s ease}
.metric-card{text-align:center;padding:10px 8px;background:#f9fafb;border-radius:10px;border:1px solid #e5e7eb}
.metric-val{font-size:24px;font-weight:800;color:#111827}
.metric-lbl{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.6px;margin-top:2px}
.log-running{border-left:3px solid #3b82f6;padding-left:10px;margin:6px 0}
</style>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  Capture print() and tag with current phase
# ═══════════════════════════════════════════════════════════════════

_current_phase = [None]

class QueueStdout:
    def __init__(self, q):
        self.q = q
        self.real = sys.stdout
    def write(self, text):
        s = text.rstrip("\n")
        if s.strip():
            ph = _current_phase[0]
            self.q.put(("PHASE_LOG", ph, s) if ph is not None else ("LOG", s))
        self.real.write(text)
    def flush(self):
        self.real.flush()


# ═══════════════════════════════════════════════════════════════════
#  Pipeline worker — mirrors run_pipeline.main() with phase tracking
# ═══════════════════════════════════════════════════════════════════

def pipeline_worker(config: dict, q: queue.Queue):
    qs = QueueStdout(q)
    orig = sys.stdout
    sys.stdout = qs

    def start(num):
        _current_phase[0] = num
        q.put(("PHASE_START", num))
    def done(num, m=None):
        _current_phase[0] = None
        q.put(("PHASE_DONE", num, m or {}))
    def skip(num):
        q.put(("PHASE_SKIP", num))
    def fail(num, err):
        _current_phase[0] = None
        q.put(("PHASE_ERROR", num, err))
    def skip_list(nums):
        for n in nums:
            skip(n)

    try:
        args = Namespace(
            countries=config.get("countries") or None,
            top_n=config.get("top_n") or None,
            refresh_gdp=config.get("refresh_gdp", False),
            cities=config.get("cities") or None,
            zones=config.get("zones") or None,
            max_scrolls=config.get("max_scrolls", 8),
            max_scrapers=config.get("max_scrapers", 3),
            skip_supabase=config.get("skip_supabase", True),
        )
        state = PipelineState()
        all_nums = [p["num"] for p in PHASES]

        # ── Entry point logic ─────────────────────────────────
        if args.zones:
            skip_list([1, 2, 3])
            dz = [z.strip() for z in args.zones.split(",") if z.strip()]
            city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
            country = args.countries.split(",")[0].strip() if args.countries else "India"
            state.master_zone_registry[(city, country)] = dz
            state.all_cities.append({"city": city, "country": country, "tier": 1})
            q.put(("LOG", f"📍 Direct Zone Mode: {len(dz)} zones in {city}, {country}"))

        elif args.cities:
            skip_list([1, 2])
            cities = [c.strip() for c in args.cities.split(",") if c.strip()]
            country = args.countries.split(",")[0].strip() if args.countries else "India"
            for cn in cities:
                state.all_cities.append({"city": cn, "country": country, "tier": 1})
            q.put(("LOG", f"📍 Direct City Mode: {len(cities)} cities"))

            start(3)
            phase_3_zone_finding(state)
            done(3, {"Zones Found": sum(len(z) for z in state.master_zone_registry.values()),
                      "Cities": len(state.master_zone_registry)})

        else:
            # ── Phase 1 ──────────────────────────────────────
            start(1)
            phase_1_gdp_ranking(state, args)
            done(1, {"Countries": len(state.gdp_ranked_countries)})

            # ── Phase 2 ──────────────────────────────────────
            start(2)
            phase_2_city_segmentation(state)
            done(2, {"Cities Found": len(state.all_cities),
                      "Countries": len(state.master_city_registry)})

            if not state.all_cities:
                fail(2, "No cities found after segmentation")
                skip_list([3, 4, 4.5, 5, 5.5])
                q.put(("RESULT", None))
                return

            # ── Phase 3 ──────────────────────────────────────
            start(3)
            phase_3_zone_finding(state)
            done(3, {"Zones Found": sum(len(z) for z in state.master_zone_registry.values()),
                      "Cities": len(state.master_zone_registry)})

        # ── Phases 4 & 5 (always run if zones exist) ─────────
        if not state.master_zone_registry:
            fail(4, "No zones found — cannot proceed")
            skip_list([4.5, 5, 5.5])
            q.put(("RESULT", None))
            return

        # ── Phase 4 ──────────────────────────────────────────
        start(4)
        phase_4_subarea_mapper(state)
        done(4, {"Sub-Areas": len(state.all_subarea_rows),
                  "Zones Mapped": len(state.master_subarea_registry)})

        # ── Phase 4.5 ───────────────────────────────────────
        start(4.5)
        if args.skip_supabase:
            skip(4.5)
        else:
            phase_4_5_supabase_insert(state, args.skip_supabase)
            done(4.5, {"Status": "Inserted"})

        # ── Phase 5 ──────────────────────────────────────────
        start(5)
        phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers)
        done(5, {"Companies": len(state.scraped_companies)})

        # ── Phase 5.5 ───────────────────────────────────────
        start(5.5)
        if args.skip_supabase:
            skip(5.5)
        else:
            phase_5_5_supabase_insert_leads(state, args.skip_supabase)
            done(5.5, {"Status": "Inserted"})

        # ── Save results ─────────────────────────────────────
        state.finalize()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(PROJECT_ROOT, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)

        result = {
            "countries_count": len(state.gdp_ranked_countries),
            "cities_count": len(state.all_cities),
            "total_zones": sum(len(z) for z in state.master_zone_registry.values()),
            "subareas_count": len(state.all_subarea_rows),
            "companies_scraped": len(state.scraped_companies),
            "failures": state.failures or [],
            "output_file": out_file,
        }
        q.put(("RESULT", result))

    except Exception as exc:
        import traceback
        cp = _current_phase[0]
        if cp is not None:
            fail(cp, str(exc))
            idx = all_nums.index(cp) if cp in all_nums else -1
            if idx >= 0:
                skip_list(all_nums[idx + 1:])
        q.put(("LOG", f"❌ Pipeline crashed:\n{traceback.format_exc()}"))
        q.put(("RESULT", None))
    finally:
        sys.stdout = orig
        _current_phase[0] = None


# ═══════════════════════════════════════════════════════════════════
#  Drain queue → update session state
# ═══════════════════════════════════════════════════════════════════

def drain_queue():
    q = st.session_state.log_queue
    ph = st.session_state.phases
    while not q.empty():
        try:
            m = q.get_nowait()
        except queue.Empty:
            break
        t = m[0]
        if t == "PHASE_START":
            ph[m[1]]["status"] = "running"
            ph[m[1]]["logs"] = []
            ph[m[1]]["error"] = None
            ph[m[1]]["metrics"] = {}
        elif t == "PHASE_DONE":
            ph[m[1]]["status"] = "done"
            ph[m[1]]["metrics"] = m[2]
        elif t == "PHASE_ERROR":
            ph[m[1]]["status"] = "error"
            ph[m[1]]["error"] = m[2]
        elif t == "PHASE_SKIP":
            ph[m[1]]["status"] = "skipped"
        elif t == "PHASE_LOG":
            ph[m[1]]["logs"].append(m[2])
        elif t == "RESULT":
            st.session_state.pipeline_result = m[1]
            if m[1] is None:
                st.session_state.pipeline_error = True
            else:
                st.session_state.pipeline_error = False
                st.session_state.pipeline_done = True
            st.session_state.pipeline_running = False


# ═══════════════════════════════════════════════════════════════════
#  Render: Overall Progress
# ═══════════════════════════════════════════════════════════════════

def render_progress():
    ph = st.session_state.phases
    active = [v for v in ph.values() if v["status"] not in ("pending", "skipped")]
    done_n = sum(1 for v in active if v["status"] == "done")
    err_n = sum(1 for v in active if v["status"] == "error")
    total = max(len(active), 1)
    pct = (done_n + err_n) / total

    if err_n:
        color = "#dc2626"
    elif st.session_state.pipeline_running:
        color = "#2563eb"
    else:
        color = "#16a34a"

    st.markdown(
        f'<div class="progress-track"><div class="progress-fill" '
        f'style="width:{pct*100:.0f}%;background:{color}"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;'
        f'margin-top:4px"><span>{done_n} of {total} phases complete'
        f'{"  •  " + str(err_n) + " failed" if err_n else ""}</span>'
        f'<span>{pct*100:.0f}%</span></div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════
#  Render: Single Phase Card
# ═══════════════════════════════════════════════════════════════════

_BADGE = {
    "pending": ("⏸", "Pending",  "b-pending"),
    "skipped": ("⏭", "Skipped",  "b-skipped"),
    "running": ("⏳", "Running",  "b-running"),
    "done":    ("✅", "Complete", "b-done"),
    "error":   ("❌", "Failed",   "b-error"),
}

def render_phase_card(info):
    num   = info["num"]
    name  = info["name"]
    icon  = info["icon"]
    desc  = info["desc"]
    p     = st.session_state.phases[num]
    st_   = p["status"]
    emoji, label, bcls = _BADGE[st_]

    # ── Card header (pure HTML) ─────────────────────────────
    st.markdown(
        f'<div class="phase-header ph-{st_}">'
        f'<table style="width:100%;border:none;cellpadding:0"><tr>'
        f'<td style="border:none;vertical-align:middle">'
        f'<span style="font-size:17px;font-weight:700;color:#000000">{icon} Phase {num}: {name}</span>'   ##Color change?
        f'<br><span style="font-size:12px;color:#6b7280">{desc}</span>'
        f'</td>'
        f'<td style="border:none;text-align:right;vertical-align:middle">'
        f'<span class="badge {bcls}">{emoji} {label}</span>'
        f'</td></tr></table></div>',
        unsafe_allow_html=True,
    )

    # ── Card body (Streamlit widgets) ───────────────────────
    if st_ == "running":
        if p["logs"]:
            st.markdown('<div class="log-running">', unsafe_allow_html=True)
            st.code("\n".join(p["logs"][-18:]), language=None)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption("⏳ Initializing…")
        # Auto-scroll
        st.markdown(
            '<script>var e=window.parent.document.querySelectorAll(".stCodeBlock");'
            'if(e.length)e[e.length-1].scrollTop=e[e.length-1].scrollHeight;</script>',
            unsafe_allow_html=True,
        )

    elif st_ == "done":
        if p["metrics"]:
            cols = st.columns(len(p["metrics"]))
            for i, (k, v) in enumerate(p["metrics"].items()):
                with cols[i]:
                    st.markdown(
                        f'<div class="metric-card"><div class="metric-val">{v}</div>'
                        f'<div class="metric-lbl">{k}</div></div>',
                        unsafe_allow_html=True,
                    )
        if p["logs"]:
            with st.expander("📋 View Logs"):
                st.code("\n".join(p["logs"]), language=None)

    elif st_ == "error":
        if p["error"]:
            st.error(f"**{p['error']}**")
        if p["logs"]:
            with st.expander("📋 View Logs", expanded=True):
                st.code("\n".join(p["logs"]), language=None)

    # Spacing between cards
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  Render: Final Results
# ═══════════════════════════════════════════════════════════════════

def render_results(r):
    st.markdown("---")
    st.subheader("📊 Final Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌍 Countries", r["countries_count"])
    c2.metric("🏙️ Cities", r["cities_count"])
    c3.metric("📍 Zones", r["total_zones"])
    c4.metric("📐 Sub-Areas", r["subareas_count"])
    st.metric("🔍 Companies Scraped", r["companies_scraped"])

    if r["failures"]:
        with st.expander(f"⚠️ {len(r['failures'])} Failure(s)"):
            for i, f in enumerate(r["failures"]):
                st.code(
                    f"#{i+1}  Phase: {f.get('phase','?')}\n"
                    f"     Instance: {f.get('instance_id','?')}\n"
                    f"     Error: {f.get('error','?')}",
                    language=None,
                )

    out = r.get("output_file", "")
    if out and os.path.exists(out):
        st.download_button(
            label="⬇  Download Results JSON",
            data=open(out, "rb").read(),
            file_name=os.path.basename(out),
            mime="application/json",
            key="dl_results",
        )


# ═══════════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🗺️ Sub-Area Mapper")
    st.caption("Master Agent Pipeline")
    st.markdown("---")

    mode = st.radio("Pipeline Mode", [
        "Full Pipeline",
        "Direct Countries",
        "Direct Cities",
        "Direct Zones",
    ], index=0, help="Choose where to start")

    ci = cc = cz = ""
    if mode == "Direct Countries":
        ci = st.text_input("Countries (comma-sep)", placeholder="India, China, USA")
    elif mode == "Direct Cities":
        cc = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi, Bangalore")
    elif mode == "Direct Zones":
        cc = st.text_input("City", value="Mumbai")
        cz = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra, Juhu")

    st.markdown("---")
    st.subheader("Parameters")
    top_n = st.number_input("Top N Countries", 1, 200, 10)
    mx_scroll = st.number_input("Max Scrolls", 1, 50, 8)
    mx_scrape = st.number_input("Max Scrapers", 1, 10, 3)
    skip_sb = st.checkbox("Skip Supabase", value=True)
    st.markdown("---")

    if st.button("▶  Start Pipeline", disabled=st.session_state.pipeline_running,
                 type="primary", use_container_width=True):
        st.session_state.phases = {p["num"]: _blank_phase() for p in PHASES}
        st.session_state.pipeline_done = False
        st.session_state.pipeline_error = None
        st.session_state.pipeline_result = None
        cfg = {
            "top_n": top_n if mode == "Full Pipeline" else None,
            "max_scrolls": mx_scroll, "max_scrapers": mx_scrape,
            "skip_supabase": skip_sb,
            "countries": ci or None, "cities": cc or None, "zones": cz or None,
        }
        st.session_state.pipeline_running = True
        st.session_state.log_queue = queue.Queue()
        t = threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.log_queue),
                             daemon=True, name="pipeline_worker")
        t.start()
        st.rerun()

    if st.button("⏹  Reset", use_container_width=True):
        st.session_state.phases = {p["num"]: _blank_phase() for p in PHASES}
        st.session_state.pipeline_running = False
        st.session_state.pipeline_done = False
        st.session_state.pipeline_error = None
        st.session_state.pipeline_result = None
        st.session_state.log_queue = queue.Queue()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
#  Main Area
# ═══════════════════════════════════════════════════════════════════

st.header("Pipeline Dashboard")
drain_queue()
render_progress()
st.markdown("<br>", unsafe_allow_html=True)

for info in PHASES:
    render_phase_card(info)

if st.session_state.pipeline_done and not st.session_state.pipeline_error:
    render_results(st.session_state.pipeline_result)

if st.session_state.pipeline_running:
    time.sleep(0.5)
    st.rerun()