# # # """
# # # ui_app.py — OxiqAI Lead Generation Agent Dashboard
# # # Exact prototype implementation: Header, Sidebar, Execute Pipeline, 
# # # Data Explorer, Agent Status, and Results Table.
# # # """

# # # import streamlit as st
# # # import threading
# # # import time
# # # import os
# # # import sys
# # # import json
# # # import pandas as pd
# # # from datetime import datetime
# # # from argparse import Namespace

# # # # ── Path setup ──────────────────────────────────────────────
# # # BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# # # sys.path.insert(0, BASE_DIR)

# # # import run_pipeline
# # # from run_pipeline import (
# # #     phase_1_gdp_ranking,
# # #     phase_2_city_segmentation,
# # #     phase_3_zone_finding,
# # #     phase_4_subarea_mapper,
# # #     phase_4_5_supabase_insert,
# # #     phase_5_lead_scraper,
# # #     phase_5_5_supabase_insert_leads,
# # # )
# # # from orchestrator_utils import PipelineState

# # # PROJECT_ROOT = run_pipeline.project_root

# # # # ── Page config ─────────────────────────────────────────────
# # # st.set_page_config(
# # #     page_title="OxiqAI Lead Generation Agent",
# # #     page_icon="🧠",
# # #     layout="wide",
# # #     initial_sidebar_state="expanded"
# # # )

# # # # ── Prototype CSS ───────────────────────────────────────────
# # # st.markdown("""<style>
# # #     /* Remove default Streamlit spacing */
# # #     .block-container { padding-top: 0rem; padding-bottom: 2rem; }
# # #     div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[style*="flex-direction: row"] { margin-top: -1rem; }
    
# # #     /* Top Header Bar */
# # #     .main-header {
# # #         display: flex; align-items: center; justify-content: space-between;
# # #         padding: 12px 30px; background-color: #0f172a; color: white;
# # #         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
# # #         border-radius: 0 0 10px 10px;
# # #     }
# # #     .header-left { display: flex; align-items: center; gap: 15px; }
# # #     .header-logo { font-size: 36px; }
# # #     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
# # #     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
# # #     .header-stage {
# # #         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
# # #         font-size: 14px; font-weight: 600; color: white;
# # #     }

# # #     /* Sidebar Styling */
# # #     section[data-testid="stSidebar"] {
# # #         background-color: #f8fafc; border-right: 1px solid #e2e8f0;
# # #     }
# # #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
# # #         background-color: #2563eb; color: white; font-weight: bold;
# # #         border-radius: 8px; padding: 12px !important;
# # #         box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
# # #     }
# # #     section[data-testid="stSidebar"] .stRadio label {
# # #         padding: 10px 12px !important; border-radius: 8px; margin-bottom: 4px;
# # #         font-size: 14px; transition: all 0.2s ease;
# # #     }
# # #     section[data-testid="stSidebar"] .stRadio label:hover {
# # #         background-color: #e2e8f0;
# # #     }

# # #     /* Cards */
# # #     .card {
# # #         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
# # #         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
# # #     }
# # #     .card-header {
# # #         font-size: 16px; font-weight: 700; color: #0f172a; 
# # #         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
# # #         display: flex; justify-content: space-between; align-items: center;
# # #     }
# # #     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

# # #     /* Agent Status Chips */
# # #     .agent-chip {
# # #         display: flex; align-items: center; padding: 10px 15px;
# # #         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
# # #         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
# # #     }
# # #     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
# # #     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
# # #     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
# # #     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

# # #     /* Data Viewers styling */
# # #     .viewer-box {
# # #         background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
# # #         padding: 10px; min-height: 150px; max-height: 300px; overflow-y: auto;
# # #         font-size: 14px; color: #334155;
# # #     }
# # # </style>""", unsafe_allow_html=True)


# # # # ── Session State Init ──────────────────────────────────────
# # # def init_session_state():
# # #     defaults = {
# # #         "page": "Dashboard",
# # #         "pipeline_running": False,
# # #         "pipeline_done": False,
# # #         "pipeline_error": False,
# # #         "pipeline_state": PipelineState(),
# # #         "agent_status": {
# # #             1: "Pending", 2: "Pending", 3: "Pending", 
# # #             4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"
# # #         },
# # #         "output_file": None
# # #     }
# # #     for key, val in defaults.items():
# # #         if key not in st.session_state:
# # #             st.session_state[key] = val

# # # init_session_state()


# # # # ── Pipeline Thread ─────────────────────────────────────────
# # # def pipeline_worker(config: dict, state: PipelineState, agent_status: dict):
# # #     args = Namespace(
# # #         countries=config.get("countries") or None,
# # #         top_n=config.get("top_n") or None,
# # #         refresh_gdp=config.get("refresh_gdp", False),
# # #         cities=config.get("cities") or None,
# # #         zones=config.get("zones") or None,
# # #         max_scrolls=config.get("max_scrolls", 8),
# # #         max_scrapers=config.get("max_scrapers", 3),
# # #         skip_supabase=config.get("skip_supabase", True),
# # #     )

# # #     # def mark(num, status): st.session_state.agent_status[num] = status
# # #     def mark(num, status): agent_status[num] = status

# # #     try:
# # #         if args.zones:
# # #             mark(1, "Skipped"); mark(2, "Skipped"); mark(3, "Skipped")
# # #             dz = [z.strip() for z in args.zones.split(",") if z.strip()]
# # #             city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
# # #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# # #             state.master_zone_registry[(city, country)] = dz
# # #             state.all_cities.append({"city": city, "country": country, "tier": 1})

# # #         elif args.cities:
# # #             mark(1, "Skipped"); mark(2, "Skipped")
# # #             cities = [c.strip() for c in args.cities.split(",") if c.strip()]
# # #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# # #             for cn in cities: state.all_cities.append({"city": cn, "country": country, "tier": 1})
            
# # #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# # #         else:
# # #             mark(1, "Running"); phase_1_gdp_ranking(state, args); mark(1, "Done")
# # #             mark(2, "Running"); phase_2_city_segmentation(state); mark(2, "Done")
# # #             if not state.all_cities: raise Exception("No cities found after Phase 2.")
# # #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# # #         if not state.master_zone_registry: raise Exception("No zones found.")
        
# # #         mark(4, "Running"); phase_4_subarea_mapper(state); mark(4, "Done")
        
# # #         if args.skip_supabase: mark(4.5, "Skipped")
# # #         else: mark(4.5, "Running"); phase_4_5_supabase_insert(state, args.skip_supabase); mark(4.5, "Done")
        
# # #         mark(5, "Running"); phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers); mark(5, "Done")
        
# # #         if args.skip_supabase: mark(5.5, "Skipped")
# # #         else: mark(5.5, "Running"); phase_5_5_supabase_insert_leads(state, args.skip_supabase); mark(5.5, "Done")

# # #         state.finalize()
# # #         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
# # #         out_dir = os.path.join(PROJECT_ROOT, "outputs")
# # #         os.makedirs(out_dir, exist_ok=True)
# # #         out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
# # #         with open(out_file, "w", encoding="utf-8") as f:
# # #             json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
        
# # #         st.session_state.output_file = out_file
# # #         st.session_state.pipeline_done = True

# # #     except Exception as e:
# # #         for k, v in agent_status.items():
# # #             if v == "Running": agent_status[k] = "Error"
# # #     finally:
# # #         st.session_state.pipeline_running = False


# # # # ── UI Components ───────────────────────────────────────────

# # # def render_header():
# # #     st.markdown('''
# # #         <div class="main-header">
# # #             <div class="header-left">
# # #                 <div class="header-logo">🧠</div>
# # #                 <div class="header-title">
# # #                     <h1>OxiqAI Lead Generation Agent</h1>
# # #                     <p>Automated B2B Database Preparation & Enrichment</p>
# # #                 </div>
# # #             </div>
# # #             <div class="header-stage">Stage 1: Active DB Preparation</div>
# # #         </div>
# # #     ''', unsafe_allow_html=True)

# # # # def render_sidebar():
# # # #     with st.sidebar:
# # # #         st.markdown("### ⚙️ Navigation")
# # # #         menu = [
# # # #             "Dashboard", 
# # # #             "Agent 1: GDP Ranker", 
# # # #             "Agent 2: City Segmenter", 
# # # #             "Agent 3: Zone Finder", 
# # # #             "Agent 4: Subarea Mapper", 
# # # #             "Agent 5: Supabase", 
# # # #             "Agent 6: Scraper"
# # # #         ]
# # # #         st.session_state.page = st.radio("", menu, label_visibility="collapsed")

# # # def render_sidebar():
# # #     with st.sidebar:
# # #         st.markdown("### ⚙️ Navigation")
# # #         menu = [
# # #             "Dashboard", 
# # #             "Agent 1: GDP Ranker", 
# # #             "Agent 2: City Segmenter", 
# # #             "Agent 3: Zone Finder", 
# # #             "Agent 4: Subarea Mapper", 
# # #             "Agent 5: Supabase", 
# # #             "Agent 6: Scraper"
# # #         ]
# # #         # FIX: Changed "" to "Hidden Navigation" to satisfy Streamlit's accessibility rules
# # #         st.session_state.page = st.radio("Hidden Navigation", menu, label_visibility="collapsed")

# # # def render_execute_card():
# # #     st.markdown('''<div class="card red-accent">
# # #         <div class="card-header">
# # #             <span>🚀 Execute Pipeline</span>
# # #         </div>''', unsafe_allow_html=True)
    
# # #     c1, c2, c3 = st.columns([3, 3, 2])
# # #     with c1:
# # #         mode = st.selectbox("Mode", ["Full Pipeline", "Direct Countries", "Direct Cities", "Direct Zones"])
# # #     with c2:
# # #         if mode == "Full Pipeline": param = st.text_input("Top N Countries", value="10")
# # #         elif mode == "Direct Countries": param = st.text_input("Countries (comma-sep)", placeholder="India, UAE")
# # #         elif mode == "Direct Cities": param = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi")
# # #         else: param = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra")
        
# # #     with c3:
# # #         st.write("<div style='height:28px'></div>", unsafe_allow_html=True)
# # #         run_btn = st.button("▶ Run Agent 1", disabled=st.session_state.pipeline_running, type="primary", use_container_width=True)
        
# # #         if run_btn:
# # #             st.session_state.pipeline_state = PipelineState()
# # #             st.session_state.pipeline_done = False
# # #             st.session_state.pipeline_error = False
# # #             st.session_state.output_file = None
# # #             st.session_state.agent_status = {1:"Pending", 2:"Pending", 3:"Pending", 4:"Pending", 4.5:"Pending", 5:"Pending", 5.5:"Pending"}
            
# # #             cfg = {
# # #                 "top_n": int(param) if mode == "Full Pipeline" and param.isdigit() else None,
# # #                 "countries": param if mode == "Direct Countries" else (param if mode == "Direct Zones" else None),
# # #                 "cities": param if mode in ["Direct Cities", "Direct Zones"] else None,
# # #                 "zones": param if mode == "Direct Zones" else None,
# # #                 "skip_supabase": True
# # #             }
# # #             # TO THIS:
# # #             st.session_state.pipeline_running = True
# # #             # Pass the actual PipelineState object to the thread so it doesn't touch session_state
# # #             threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.pipeline_state, st.session_state.agent_status), daemon=True).start()

# # #     if st.session_state.pipeline_running:
# # #         st.info("⏳ Pipeline is running in background. View status below.")
# # #     elif st.session_state.pipeline_error:
# # #         st.error(f"❌ Failed: {st.session_state.pipeline_error}")
        
# # #     st.markdown('</div>', unsafe_allow_html=True)

# # # def render_data_explorer():
# # #     st.markdown('''<div class="card">
# # #         <div class="card-header"><span>📂 Select & View Data</span></div>''', unsafe_allow_html=True)
    
# # #     state = st.session_state.pipeline_state
    
# # #     # Extract lists safely
# # #     countries = sorted(list(set([c.get("country") for c in state.all_cities])))
    
# # #     # Create 4 columns for Select/View pairs
# # #     col_c_sel, col_c_view, col_ci_sel, col_ci_view = st.columns(4)
    
# # #     with col_c_sel:
# # #         sel_country = st.selectbox("Select Country", ["--"] + countries)
# # #     with col_c_view:
# # #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If country not available, execute Agent 1</div>", unsafe_allow_html=True)
        
# # #     # Filter cities based on selected country
# # #     filtered_cities = []
# # #     if sel_country != "--":
# # #         filtered_cities = sorted([c.get("city") for c in state.all_cities if c.get("country") == sel_country])
        
# # #     with col_ci_sel:
# # #         sel_city = st.selectbox("Select City", ["--"] + filtered_cities)
# # #     with col_ci_view:
# # #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If city not available, execute Agent 2</div>", unsafe_allow_html=True)

# # #     # Row 2: Zones and Subareas
# # #     col_z_sel, col_z_view, col_sa_sel, col_sa_view = st.columns(4)
    
# # #     filtered_zones = []
# # #     if sel_city != "--" and sel_country != "--":
# # #         filtered_zones = state.master_zone_registry.get((sel_city, sel_country), [])
        
# # #     with col_z_sel:
# # #         sel_zone = st.selectbox("Select Zone", ["--"] + filtered_zones)
# # #     with col_z_view:
# # #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If zone not available, execute Agent 3</div>", unsafe_allow_html=True)
        
# # #     filtered_subareas = []
# # #     if sel_zone != "--" and sel_city != "--" and sel_country != "--":
# # #         sa_list = state.master_subarea_registry.get((sel_zone, sel_city, sel_country), [])
# # #         filtered_subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

# # #     with col_sa_sel:
# # #         sel_subarea = st.selectbox("Select Subarea", ["--"] + filtered_subareas)
# # #     with col_sa_view:
# # #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If subarea not available, execute Agent 4</div>", unsafe_allow_html=True)

# # #     st.markdown('</div>', unsafe_allow_html=True)
# # #     return sel_country, sel_city, sel_zone, sel_subarea

# # # def render_bottom_section(sel_country, sel_city, sel_zone, sel_subarea):
# # #     status_col, table_col = st.columns([1, 2.5])
    
# # #     # LEFT: Agent Status
# # #     with status_col:
# # #         st.markdown('''<div class="card">
# # #             <div class="card-header"><span>📊 Status</span></div>''', unsafe_allow_html=True)
            
# # #         agents = [
# # #             (1, "GDP Ranker"), (2, "City Segmenter"), (3, "Zone Finder"),
# # #             (4, "Subarea Mapper"), (5, "Company Scraper")
# # #         ]
# # #         for num, name in agents:
# # #             status = st.session_state.agent_status.get(num, "Pending")
# # #             cls = "agent-chip"
# # #             if status == "Running": cls += " agent-running"
# # #             elif status == "Done": cls += " agent-done"
# # #             elif status == "Error": cls += " agent-error"
            
# # #             icon = {"Pending": "⏸", "Running": "⏳", "Done": "✅", "Skipped": "⏭", "Error": "❌"}.get(status, "")
# # #             st.markdown(f'<div class="{cls}">{icon} Agent {num} is {status}</div>', unsafe_allow_html=True)
            
# # #         st.markdown('</div>', unsafe_allow_html=True)

# # #     # RIGHT: Results Table
# # #     with table_col:
# # #         st.markdown('''<div class="card">
# # #             <div class="card-header">
# # #                 <span>🏢 Resultant Company Data</span>
# # #             </div>''', unsafe_allow_html=True)
        
# # #         companies = st.session_state.pipeline_state.scraped_companies
        
# # #         # Dynamic Filtering based on selection
# # #         if sel_subarea != "--":
# # #             companies = [c for c in companies if c.get("subarea_name") == sel_subarea]
# # #         elif sel_zone != "--":
# # #             companies = [c for c in companies if c.get("zone_name") == sel_zone]
# # #         elif sel_city != "--":
# # #             companies = [c for c in companies if c.get("city_name") == sel_city]
# # #         elif sel_country != "--":
# # #             companies = [c for c in companies if c.get("country_name") == sel_country]

# # #         if companies:
# # #             df = pd.DataFrame(companies)
# # #             # Ensure standard columns exist for clean viewing
# # #             standard_cols = ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name", "country_name"]
# # #             existing_cols = [c for c in standard_cols if c in df.columns]
# # #             st.dataframe(df[existing_cols].reset_index(drop=True), use_container_width=True, height=300)
            
# # #             if st.session_state.output_file and os.path.exists(st.session_state.output_file):
# # #                 with open(st.session_state.output_file, "rb") as f:
# # #                     st.download_button("⬇ Download Full Results JSON", f, file_name="leads_results.json")
# # #         else:
# # #             if st.session_state.pipeline_done:
# # #                 st.info("No companies found for this specific filter.")
# # #             else:
# # #                 st.warning("Company data will appear here in a table format after executing the pipeline.")
                
# # #         st.markdown('</div>', unsafe_allow_html=True)


# # # # ── Main App Assembly ───────────────────────────────────────

# # # render_header()
# # # render_sidebar()

# # # if st.session_state.page == "Dashboard":
# # #     render_execute_card()
# # #     sel_c, sel_ci, sel_z, sel_sa = render_data_explorer()
# # #     render_bottom_section(sel_c, sel_ci, sel_z, sel_sa)
# # # else:
# # #     # Fallback for individual agent pages clicked in sidebar
# # #     st.markdown(f'''
# # #         <div class="card">
# # #             <div class="card-header"><span>{st.session_state.page}</span></div>
# # #             <p>Specific configurations and logs for this agent will be integrated here.</p>
# # #             <p>To run the full sequential workflow, please navigate back to <b>Dashboard</b> and click "Run Agent 1".</p>
# # #         </div>
# # #     ''', unsafe_allow_html=True)

# # # # Trigger UI refresh while pipeline is running in background
# # # if st.session_state.pipeline_running:
# # #     time.sleep(1)
# # #     st.rerun()


# # # ----------------------------------------------------------------------------------------------


# # """
# # ui_app.py — OxiqAI Lead Generation Agent Dashboard
# # Exact prototype implementation: Header, Sidebar, Execute Pipeline, 
# # Data Explorer, Agent Status, and Results Table.
# # """

# # import streamlit as st
# # import threading
# # import time
# # import os
# # import sys
# # import json
# # import pandas as pd
# # from datetime import datetime
# # from argparse import Namespace

# # # ── Path setup ──────────────────────────────────────────────
# # BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# # sys.path.insert(0, BASE_DIR)

# # import run_pipeline
# # from run_pipeline import (
# #     phase_1_gdp_ranking,
# #     phase_2_city_segmentation,
# #     phase_3_zone_finding,
# #     phase_4_subarea_mapper,
# #     phase_4_5_supabase_insert,
# #     phase_5_lead_scraper,
# #     phase_5_5_supabase_insert_leads,
# # )
# # from orchestrator_utils import PipelineState

# # PROJECT_ROOT = run_pipeline.project_root

# # # ── Page config ─────────────────────────────────────────────
# # st.set_page_config(
# #     page_title="OxiqAI Lead Generation Agent",
# #     page_icon="🧠",
# #     layout="wide",
# #     initial_sidebar_state="expanded"
# # )

# # # ── Prototype CSS ───────────────────────────────────────────
# # # st.markdown("""<style>
# # #     /* Remove default Streamlit spacing */
# # #     .block-container { padding-top: 0rem; padding-bottom: 2rem; }
# # #     div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[style*="flex-direction: row"] { margin-top: -1rem; }
    
# # #     /* Top Header Bar */
# # #     .main-header {
# # #         display: flex; align-items: center; justify-content: space-between;
# # #         padding: 12px 30px; background-color: #0f172a; color: white;
# # #         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
# # #         border-radius: 0 0 10px 10px;
# # #     }
# # #     .header-left { display: flex; align-items: center; gap: 15px; }
# # #     .header-logo { font-size: 36px; }
# # #     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
# # #     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
# # #     .header-stage {
# # #         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
# # #         font-size: 14px; font-weight: 600; color: white;
# # #     }

    
# # #         /* Sidebar Styling */
# # #     section[data-testid="stSidebar"] {
# # #         background-color: #f8fafc; border-right: 1px solid #e2e8f0;
# # #     }
    
# # #     /* FORCE unselected text to be black */
# # #     section[data-testid="stSidebar"] .stRadio p {
# # #         color: #000000 !important;
# # #         font-weight: 500 !important;
# # #     }

# # #     /* FORCE selected text to stay white on the blue background */
# # #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] p {
# # #         color: #ffffff !important;
# # #         font-weight: bold !important;
# # #     }

# # #     /* Selected blue background styling */
# # #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
# # #         background-color: #2563eb !important; 
# # #         border-radius: 8px; padding: 12px !important;
# # #         box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
# # #     }
    
# # #     /* General spacing */
# # #     section[data-testid="stSidebar"] .stRadio label {
# # #         padding: 10px 12px !important; border-radius: 8px; margin-bottom: 4px;
# # #     }

# # #     /* Cards */
# # #     .card {
# # #         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
# # #         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
# # #     }
# # #     .card-header {
# # #         font-size: 16px; font-weight: 700; color: #0f172a; 
# # #         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
# # #         display: flex; justify-content: space-between; align-items: center;
# # #     }
# # #     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

# # #     /* Agent Status Chips */
# # #     .agent-chip {
# # #         display: flex; align-items: center; padding: 10px 15px;
# # #         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
# # #         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
# # #     }
# # #     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
# # #     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
# # #     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
# # #     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

# # #     /* Data Viewers styling */
# # #     .viewer-box {
# # #         background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
# # #         padding: 10px; min-height: 150px; max-height: 300px; overflow-y: auto;
# # #         font-size: 14px; color: #334155;
# # #     }
# # # </style>""", unsafe_allow_html=True)

# # st.markdown("""<style>
# #     /* 1. FIX: Pull the top header down so it doesn't get cut off */
# #     .block-container { 
# #         padding-top: 1rem; 
# #         padding-bottom: 2rem; 
# #     }
# #     .main-header {
# #         margin-top: 30px; /* Drags header up into the empty space safely */
# #     }

# #     /* 2. Top Header Bar Styling */
# #     .main-header {
# #         display: flex; align-items: center; justify-content: space-between;
# #         padding: 15px 30px; background-color: #0f172a; color: white;
# #         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
# #         border-radius: 0 0 10px 10px;
# #     }
# #     .header-left { display: flex; align-items: center; gap: 15px; }
# #     .header-logo { font-size: 36px; }
# #     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
# #     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
# #     .header-stage {
# #         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
# #         font-size: 14px; font-weight: 600; color: white;
# #     }

# #     /* 3. FIX: Force BLACK text on white sidebar (bulletproof) */
# #     section[data-testid="stSidebar"] {
# #         background-color: #f8fafc; border-right: 1px solid #e2e8f0;
# #     }
# #     section[data-testid="stSidebar"] * {
# #         color: #000000 !important; /* Forces everything black */
# #     }
    
# #     /* 4. Override ONLY the selected sidebar item to be WHITE on BLUE */
# #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
# #         background-color: #2563eb !important; 
# #         border-radius: 8px; padding: 12px !important;
# #         box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
# #     }
# #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] * {
# #         color: #ffffff !important; /* Forces selected text back to white */
# #         font-weight: bold !important;
# #     }
    
# #     /* 5. Sidebar spacing */
# #     section[data-testid="stSidebar"] .stRadio label {
# #         padding: 10px 12px !important; border-radius: 8px; margin-bottom: 4px;
# #     }

# #     /* 6. Cards */
# #     .card {
# #         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
# #         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
# #     }
# #     .agent-text { color: #000000 !important; font-size: 15px; line-height: 1.6; }
# #     .card-header {
# #         font-size: 16px; font-weight: 700; color: #0f172a; 
# #         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
# #         display: flex; justify-content: space-between; align-items: center;
# #     }
# #     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

# #     /* 7. Agent Status Chips */
# #     .agent-chip {
# #         display: flex; align-items: center; padding: 10px 15px;
# #         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
# #         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
# #     }
# #     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
# #     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
# #     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
# #     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
# # </style>""", unsafe_allow_html=True)


# # # ── Session State Init ──────────────────────────────────────
# # def init_session_state():
# #     defaults = {
# #         "page": "Dashboard",
# #         "pipeline_running": False,
# #         "pipeline_done": False,
# #         "pipeline_error": False,
# #         "pipeline_state": PipelineState(),
# #         "agent_status": {
# #             1: "Pending", 2: "Pending", 3: "Pending", 
# #             4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"
# #         },
# #         "output_file": None
# #     }
# #     for key, val in defaults.items():
# #         if key not in st.session_state:
# #             st.session_state[key] = val

# # init_session_state()


# # # ── Pipeline Thread ─────────────────────────────────────────
# # def pipeline_worker(config: dict, state: PipelineState, agent_status: dict):
# #     args = Namespace(
# #         countries=config.get("countries") or None,
# #         top_n=config.get("top_n") or None,
# #         refresh_gdp=config.get("refresh_gdp", False),
# #         cities=config.get("cities") or None,
# #         zones=config.get("zones") or None,
# #         max_scrolls=config.get("max_scrolls", 8),
# #         max_scrapers=config.get("max_scrapers", 3),
# #         skip_supabase=config.get("skip_supabase", True),
# #     )

# #     def mark(num, status): agent_status[num] = status

# #     try:
# #         if args.zones:
# #             mark(1, "Skipped"); mark(2, "Skipped"); mark(3, "Skipped")
# #             dz = [z.strip() for z in args.zones.split(",") if z.strip()]
# #             city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
# #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# #             state.master_zone_registry[(city, country)] = dz
# #             state.all_cities.append({"city": city, "country": country, "tier": 1})

# #         elif args.cities:
# #             mark(1, "Skipped"); mark(2, "Skipped")
# #             cities = [c.strip() for c in args.cities.split(",") if c.strip()]
# #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# #             for cn in cities: state.all_cities.append({"city": cn, "country": country, "tier": 1})
            
# #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# #         else:
# #             mark(1, "Running"); phase_1_gdp_ranking(state, args); mark(1, "Done")
# #             mark(2, "Running"); phase_2_city_segmentation(state); mark(2, "Done")
# #             if not state.all_cities: raise Exception("No cities found after Phase 2.")
# #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# #         if not state.master_zone_registry: raise Exception("No zones found.")
        
# #         mark(4, "Running"); phase_4_subarea_mapper(state); mark(4, "Done")
        
# #         if args.skip_supabase: mark(4.5, "Skipped")
# #         else: mark(4.5, "Running"); phase_4_5_supabase_insert(state, args.skip_supabase); mark(4.5, "Done")
        
# #         mark(5, "Running"); phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers); mark(5, "Done")
        
# #         if args.skip_supabase: mark(5.5, "Skipped")
# #         else: mark(5.5, "Running"); phase_5_5_supabase_insert_leads(state, args.skip_supabase); mark(5.5, "Done")

# #         state.finalize()
# #         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
# #         out_dir = os.path.join(PROJECT_ROOT, "outputs")
# #         os.makedirs(out_dir, exist_ok=True)
# #         out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
# #         with open(out_file, "w", encoding="utf-8") as f:
# #             json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
        
# #         st.session_state.output_file = out_file
# #         st.session_state.pipeline_done = True

# #     except Exception as e:
# #         for k, v in agent_status.items():
# #             if v == "Running": agent_status[k] = "Error"
# #     finally:
# #         st.session_state.pipeline_running = False


# # # ── UI Components ───────────────────────────────────────────

# # def render_header():
# #     st.markdown('''
# #         <div class="main-header">
# #             <div class="header-left">
# #                 <div class="header-logo">🧠</div>
# #                 <div class="header-title">
# #                     <h1>OxiqAI Lead Generation Agent</h1>
# #                     <p>Automated B2B Database Preparation & Enrichment</p>
# #                 </div>
# #             </div>
# #             <div class="header-stage">Stage 1: Active DB Preparation</div>
# #         </div>
# #     ''', unsafe_allow_html=True)

# # def render_sidebar():
# #     with st.sidebar:
# #         st.markdown("### ⚙️ Navigation")
# #         menu = [
# #             "Dashboard", 
# #             "Agent 1: GDP Ranker", 
# #             "Agent 2: City Segmenter", 
# #             "Agent 3: Zone Finder", 
# #             "Agent 4: Subarea Mapper", 
# #             "Agent 5: Supabase", 
# #             "Agent 6: Scraper"
# #         ]
# #         # FIX: Changed "" to "Hidden Navigation" to satisfy Streamlit's accessibility rules
# #         st.session_state.page = st.radio("Hidden Navigation", menu, label_visibility="collapsed")

# # def render_execute_card():
# #     st.markdown('''<div class="card red-accent">
# #         <div class="card-header">
# #             <span>🚀 Execute Pipeline</span>
# #         </div>''', unsafe_allow_html=True)
    
# #     c1, c2, c3 = st.columns([3, 3, 2])
# #     with c1:
# #         mode = st.selectbox("Mode", ["Full Pipeline", "Direct Countries", "Direct Cities", "Direct Zones"])
# #     with c2:
# #         if mode == "Full Pipeline": param = st.text_input("Top N Countries", value="10")
# #         elif mode == "Direct Countries": param = st.text_input("Countries (comma-sep)", placeholder="India, UAE")
# #         elif mode == "Direct Cities": param = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi")
# #         else: param = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra")
        
# #     with c3:
# #         st.write("<div style='height:28px'></div>", unsafe_allow_html=True)
# #         run_btn = st.button("▶ Run Agent 1", disabled=st.session_state.pipeline_running, type="primary", width="stretch")
        
# #         if run_btn:
# #             st.session_state.pipeline_state = PipelineState()
# #             st.session_state.pipeline_done = False
# #             st.session_state.pipeline_error = False
# #             st.session_state.output_file = None
# #             st.session_state.agent_status = {1:"Pending", 2:"Pending", 3:"Pending", 4:"Pending", 4.5:"Pending", 5:"Pending", 5.5:"Pending"}
            
# #             cfg = {
# #                 "top_n": int(param) if mode == "Full Pipeline" and param.isdigit() else None,
# #                 "countries": param if mode == "Direct Countries" else (param if mode == "Direct Zones" else None),
# #                 "cities": param if mode in ["Direct Cities", "Direct Zones"] else None,
# #                 "zones": param if mode == "Direct Zones" else None,
# #                 "skip_supabase": True
# #             }
# #             st.session_state.pipeline_running = True
# #             # Pass the actual PipelineState object to the thread so it doesn't touch session_state
# #             threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.pipeline_state, st.session_state.agent_status), daemon=True).start()

# #     if st.session_state.pipeline_running:
# #         st.info("⏳ Pipeline is running in background. View status below.")
# #     elif st.session_state.pipeline_error:
# #         st.error(f"❌ Failed: {st.session_state.pipeline_error}")
        
# #     st.markdown('</div>', unsafe_allow_html=True)

# # def render_data_explorer():
# #     st.markdown('''<div class="card">
# #         <div class="card-header"><span>📂 Select & View Data</span></div>''', unsafe_allow_html=True)
    
# #     state = st.session_state.pipeline_state
    
# #     # Extract lists safely
# #     countries = sorted(list(set([c.get("country") for c in state.all_cities])))
    
# #     # Create 4 columns for Select/View pairs
# #     col_c_sel, col_c_view, col_ci_sel, col_ci_view = st.columns(4)
    
# #     with col_c_sel:
# #         sel_country = st.selectbox("Select Country", ["--"] + countries)
# #     with col_c_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If country not available, execute Agent 1</div>", unsafe_allow_html=True)
        
# #     # Filter cities based on selected country
# #     filtered_cities = []
# #     if sel_country != "--":
# #         filtered_cities = sorted([c.get("city") for c in state.all_cities if c.get("country") == sel_country])
        
# #     with col_ci_sel:
# #         sel_city = st.selectbox("Select City", ["--"] + filtered_cities)
# #     with col_ci_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If city not available, execute Agent 2</div>", unsafe_allow_html=True)

# #     # Row 2: Zones and Subareas
# #     col_z_sel, col_z_view, col_sa_sel, col_sa_view = st.columns(4)
    
# #     filtered_zones = []
# #     if sel_city != "--" and sel_country != "--":
# #         filtered_zones = state.master_zone_registry.get((sel_city, sel_country), [])
        
# #     with col_z_sel:
# #         sel_zone = st.selectbox("Select Zone", ["--"] + filtered_zones)
# #     with col_z_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If zone not available, execute Agent 3</div>", unsafe_allow_html=True)
        
# #     filtered_subareas = []
# #     if sel_zone != "--" and sel_city != "--" and sel_country != "--":
# #         sa_list = state.master_subarea_registry.get((sel_zone, sel_city, sel_country), [])
# #         filtered_subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

# #     with col_sa_sel:
# #         sel_subarea = st.selectbox("Select Subarea", ["--"] + filtered_subareas)
# #     with col_sa_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If subarea not available, execute Agent 4</div>", unsafe_allow_html=True)

# #     st.markdown('</div>', unsafe_allow_html=True)
# #     return sel_country, sel_city, sel_zone, sel_subarea

# # def render_bottom_section(sel_country, sel_city, sel_zone, sel_subarea):
# #     status_col, table_col = st.columns([1, 2.5])
    
# #     # LEFT: Agent Status
# #     with status_col:
# #         st.markdown('''<div class="card">
# #             <div class="card-header"><span>📊 Status</span></div>''', unsafe_allow_html=True)
            
# #         agents = [
# #             (1, "GDP Ranker"), (2, "City Segmenter"), (3, "Zone Finder"),
# #             (4, "Subarea Mapper"), (5, "Company Scraper")
# #         ]
# #         for num, name in agents:
# #             status = st.session_state.agent_status.get(num, "Pending")
# #             cls = "agent-chip"
# #             if status == "Running": cls += " agent-running"
# #             elif status == "Done": cls += " agent-done"
# #             elif status == "Error": cls += " agent-error"
            
# #             icon = {"Pending": "⏸", "Running": "⏳", "Done": "✅", "Skipped": "⏭", "Error": "❌"}.get(status, "")
# #             st.markdown(f'<div class="{cls}">{icon} Agent {num} is {status}</div>', unsafe_allow_html=True)
            
# #         st.markdown('</div>', unsafe_allow_html=True)

# #     # RIGHT: Results Table
# #     with table_col:
# #         st.markdown('''<div class="card">
# #             <div class="card-header">
# #                 <span>🏢 Resultant Company Data</span>
# #             </div>''', unsafe_allow_html=True)
        
# #         companies = st.session_state.pipeline_state.scraped_companies
        
# #         # Dynamic Filtering based on selection
# #         if sel_subarea != "--":
# #             companies = [c for c in companies if c.get("subarea_name") == sel_subarea]
# #         elif sel_zone != "--":
# #             companies = [c for c in companies if c.get("zone_name") == sel_zone]
# #         elif sel_city != "--":
# #             companies = [c for c in companies if c.get("city_name") == sel_city]
# #         elif sel_country != "--":
# #             companies = [c for c in companies if c.get("country_name") == sel_country]

# #         if companies:
# #             df = pd.DataFrame(companies)
# #             # Ensure standard columns exist for clean viewing
# #             standard_cols = ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name", "country_name"]
# #             existing_cols = [c for c in standard_cols if c in df.columns]
# #             st.dataframe(df[existing_cols].reset_index(drop=True), width="stretch", height=300)
            
# #             if st.session_state.output_file and os.path.exists(st.session_state.output_file):
# #                 with open(st.session_state.output_file, "rb") as f:
# #                     st.download_button("⬇ Download Full Results JSON", f, file_name="leads_results.json")
# #         else:
# #             if st.session_state.pipeline_done:
# #                 st.info("No companies found for this specific filter.")
# #             else:
# #                 st.warning("Company data will appear here in a table format after executing the pipeline.")
                
# #         st.markdown('</div>', unsafe_allow_html=True)


# # # ----------------------Individual Page Results--------------------------------------

# # # ── Render Individual Agent Pages ──────────────────────────
# # def render_agent_page(page_name):
# #     state = st.session_state.pipeline_state
    
# #     # Determine agent number for status badge
# #     status_map = {"Agent 1": 1, "Agent 2": 2, "Agent 3": 3, "Agent 4": 4, "Agent 5": 4.5, "Agent 6": 5}
# #     agent_num = next((num for name, num in status_map.items() if name in page_name), None)
# #     agent_status = st.session_state.agent_status.get(agent_num, "Pending") if agent_num else "Unknown"
    
# #     # Render Header Card with forced black text
# #     st.markdown(f'''
# #         <div class="card">
# #             <div class="card-header">
# #                 <span class="agent-text">{page_name}</span>
# #                 <span style="background:#f1f5f9; color:#000; padding:5px 12px; border-radius:8px; font-weight:600; font-size:13px;">
# #                     Status: {agent_status}
# #                 </span>
# #             </div>
# #         </div>
# #     ''', unsafe_allow_html=True)

# #     # Render Results based on which agent was clicked
# #     if "Agent 1" in page_name:
# #         data = state.gdp_ranked_countries
# #         if data:
# #             st.dataframe(pd.DataFrame(data), width="stretch")
# #         else:
# #             st.markdown('<p class="agent-text">No GDP data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# #     elif "Agent 2" in page_name:
# #         data = state.all_cities
# #         if data:
# #             st.dataframe(pd.DataFrame(data), width="stretch")
# #         else:
# #             st.markdown('<p class="agent-text">No city data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# #     elif "Agent 3" in page_name:
# #         # Flatten the zone registry dictionary into a table format
# #         zone_rows = []
# #         for (city, country), zones in state.master_zone_registry.items():
# #             for z in zones:
# #                 zone_rows.append({"Country": country, "City": city, "Zone Name": z})
# #         if zone_rows:
# #             st.dataframe(pd.DataFrame(zone_rows), width="stretch")
# #         else:
# #             st.markdown('<p class="agent-text">No zone data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# #     elif "Agent 4" in page_name:
# #         data = state.all_subarea_rows
# #         if data:
# #             # Select common columns to keep the table clean
# #             cols = [c for c in ["zone_name", "subarea_name", "city", "country", "business_volume", "status"] if c in data[0]]
# #             st.dataframe(pd.DataFrame(data)[cols], width="stretch")
# #         else:
# #             st.markdown('<p class="agent-text">No sub-area data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# #     elif "Agent 5" in page_name:
# #         st.markdown('<p class="agent-text">Supabase insertion status.</p>', unsafe_allow_html=True)
# #         st.markdown(f'<p class="agent-text"><b>Subareas Insert:</b> {st.session_state.agent_status.get(4.5, "Pending")}</p>', unsafe_allow_html=True)
# #         st.markdown(f'<p class="agent-text"><b>Leads Insert:</b> {st.session_state.agent_status.get(5.5, "Pending")}</p>', unsafe_allow_html=True)

# #     elif "Agent 6" in page_name:
# #         data = state.scraped_companies
# #         if data:
# #             cols = [c for c in ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name"] if c in data[0]]
# #             st.dataframe(pd.DataFrame(data)[cols], width="stretch")
# #         else:
# #             st.markdown('<p class="agent-text">No scraped company data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# # # ── Main App Assembly ───────────────────────────────────────

# # render_header()
# # render_sidebar()

# # if st.session_state.page == "Dashboard":
# #     render_execute_card()
# #     sel_c, sel_ci, sel_z, sel_sa = render_data_explorer()
# #     render_bottom_section(sel_c, sel_ci, sel_z, sel_sa)
# # # else:
# # #     # Fallback for individual agent pages clicked in sidebar
# # #     st.markdown(f'''
# # #         <div class="card">
# # #             <div class="card-header"><span>{st.session_state.page}</span></div>
# # #             <p>Specific configurations and logs for this agent will be integrated here.</p>
# # #             <p>To run the full sequential workflow, please navigate back to <b>Dashboard</b> and click "Run Agent 1".</p>
# # #         </div>
# # #     ''', unsafe_allow_html=True)
# # else:
# #     # Show individual agent data
# #     render_agent_page(st.session_state.page)

# # # Trigger UI refresh while pipeline is running in background
# # if st.session_state.pipeline_running:
# #     time.sleep(1)
# #     st.rerun()



# # -------------------------------------------------------------------------------------------




# # """
# # ui_app.py — OxiqAI Lead Generation Agent Dashboard
# # Exact prototype implementation: Header, Sidebar, Execute Pipeline, 
# # Data Explorer, Agent Status, and Results Table.
# # """

# # import streamlit as st
# # import threading
# # import time
# # import os
# # import sys
# # import json
# # import pandas as pd
# # from datetime import datetime
# # from argparse import Namespace

# # # ── Path setup ──────────────────────────────────────────────
# # BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# # sys.path.insert(0, BASE_DIR)

# # import run_pipeline
# # from run_pipeline import (
# #     phase_1_gdp_ranking,
# #     phase_2_city_segmentation,
# #     phase_3_zone_finding,
# #     phase_4_subarea_mapper,
# #     phase_4_5_supabase_insert,
# #     phase_5_lead_scraper,
# #     phase_5_5_supabase_insert_leads,
# # )
# # from orchestrator_utils import PipelineState

# # PROJECT_ROOT = run_pipeline.project_root

# # # ── Page config ─────────────────────────────────────────────
# # st.set_page_config(
# #     page_title="OxiqAI Lead Generation Agent",
# #     page_icon="🧠",
# #     layout="wide",
# #     initial_sidebar_state="expanded"
# # )

# # # ── Prototype CSS ───────────────────────────────────────────
# # st.markdown("""<style>
# #     /* Remove default Streamlit spacing */
# #     .block-container { padding-top: 0rem; padding-bottom: 2rem; }
# #     div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[style*="flex-direction: row"] { margin-top: -1rem; }
    
# #     /* Top Header Bar */
# #     .main-header {
# #         display: flex; align-items: center; justify-content: space-between;
# #         padding: 12px 30px; background-color: #0f172a; color: white;
# #         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
# #         border-radius: 0 0 10px 10px;
# #     }
# #     .header-left { display: flex; align-items: center; gap: 15px; }
# #     .header-logo { font-size: 36px; }
# #     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
# #     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
# #     .header-stage {
# #         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
# #         font-size: 14px; font-weight: 600; color: white;
# #     }

# #     /* Sidebar Styling */
# #     section[data-testid="stSidebar"] {
# #         background-color: #f8fafc; border-right: 1px solid #e2e8f0;
# #     }
# #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
# #         background-color: #2563eb; color: white; font-weight: bold;
# #         border-radius: 8px; padding: 12px !important;
# #         box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
# #     }
# #     section[data-testid="stSidebar"] .stRadio label {
# #         padding: 10px 12px !important; border-radius: 8px; margin-bottom: 4px;
# #         font-size: 14px; transition: all 0.2s ease;
# #     }
# #     section[data-testid="stSidebar"] .stRadio label:hover {
# #         background-color: #e2e8f0;
# #     }

# #     /* Cards */
# #     .card {
# #         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
# #         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
# #     }
# #     .card-header {
# #         font-size: 16px; font-weight: 700; color: #0f172a; 
# #         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
# #         display: flex; justify-content: space-between; align-items: center;
# #     }
# #     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

# #     /* Agent Status Chips */
# #     .agent-chip {
# #         display: flex; align-items: center; padding: 10px 15px;
# #         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
# #         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
# #     }
# #     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
# #     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
# #     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
# #     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

# #     /* Data Viewers styling */
# #     .viewer-box {
# #         background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
# #         padding: 10px; min-height: 150px; max-height: 300px; overflow-y: auto;
# #         font-size: 14px; color: #334155;
# #     }
# # </style>""", unsafe_allow_html=True)


# # # ── Session State Init ──────────────────────────────────────
# # def init_session_state():
# #     defaults = {
# #         "page": "Dashboard",
# #         "pipeline_running": False,
# #         "pipeline_done": False,
# #         "pipeline_error": False,
# #         "pipeline_state": PipelineState(),
# #         "agent_status": {
# #             1: "Pending", 2: "Pending", 3: "Pending", 
# #             4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"
# #         },
# #         "output_file": None
# #     }
# #     for key, val in defaults.items():
# #         if key not in st.session_state:
# #             st.session_state[key] = val

# # init_session_state()


# # # ── Pipeline Thread ─────────────────────────────────────────
# # def pipeline_worker(config: dict, state: PipelineState, agent_status: dict):
# #     args = Namespace(
# #         countries=config.get("countries") or None,
# #         top_n=config.get("top_n") or None,
# #         refresh_gdp=config.get("refresh_gdp", False),
# #         cities=config.get("cities") or None,
# #         zones=config.get("zones") or None,
# #         max_scrolls=config.get("max_scrolls", 8),
# #         max_scrapers=config.get("max_scrapers", 3),
# #         skip_supabase=config.get("skip_supabase", True),
# #     )

# #     # def mark(num, status): st.session_state.agent_status[num] = status
# #     def mark(num, status): agent_status[num] = status

# #     try:
# #         if args.zones:
# #             mark(1, "Skipped"); mark(2, "Skipped"); mark(3, "Skipped")
# #             dz = [z.strip() for z in args.zones.split(",") if z.strip()]
# #             city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
# #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# #             state.master_zone_registry[(city, country)] = dz
# #             state.all_cities.append({"city": city, "country": country, "tier": 1})

# #         elif args.cities:
# #             mark(1, "Skipped"); mark(2, "Skipped")
# #             cities = [c.strip() for c in args.cities.split(",") if c.strip()]
# #             country = args.countries.split(",")[0].strip() if args.countries else "India"
# #             for cn in cities: state.all_cities.append({"city": cn, "country": country, "tier": 1})
            
# #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# #         else:
# #             mark(1, "Running"); phase_1_gdp_ranking(state, args); mark(1, "Done")
# #             mark(2, "Running"); phase_2_city_segmentation(state); mark(2, "Done")
# #             if not state.all_cities: raise Exception("No cities found after Phase 2.")
# #             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

# #         if not state.master_zone_registry: raise Exception("No zones found.")
        
# #         mark(4, "Running"); phase_4_subarea_mapper(state); mark(4, "Done")
        
# #         if args.skip_supabase: mark(4.5, "Skipped")
# #         else: mark(4.5, "Running"); phase_4_5_supabase_insert(state, args.skip_supabase); mark(4.5, "Done")
        
# #         mark(5, "Running"); phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers); mark(5, "Done")
        
# #         if args.skip_supabase: mark(5.5, "Skipped")
# #         else: mark(5.5, "Running"); phase_5_5_supabase_insert_leads(state, args.skip_supabase); mark(5.5, "Done")

# #         state.finalize()
# #         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
# #         out_dir = os.path.join(PROJECT_ROOT, "outputs")
# #         os.makedirs(out_dir, exist_ok=True)
# #         out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
# #         with open(out_file, "w", encoding="utf-8") as f:
# #             json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
        
# #         st.session_state.output_file = out_file
# #         st.session_state.pipeline_done = True

# #     except Exception as e:
# #         for k, v in agent_status.items():
# #             if v == "Running": agent_status[k] = "Error"
# #     finally:
# #         st.session_state.pipeline_running = False


# # # ── UI Components ───────────────────────────────────────────

# # def render_header():
# #     st.markdown('''
# #         <div class="main-header">
# #             <div class="header-left">
# #                 <div class="header-logo">🧠</div>
# #                 <div class="header-title">
# #                     <h1>OxiqAI Lead Generation Agent</h1>
# #                     <p>Automated B2B Database Preparation & Enrichment</p>
# #                 </div>
# #             </div>
# #             <div class="header-stage">Stage 1: Active DB Preparation</div>
# #         </div>
# #     ''', unsafe_allow_html=True)

# # # def render_sidebar():
# # #     with st.sidebar:
# # #         st.markdown("### ⚙️ Navigation")
# # #         menu = [
# # #             "Dashboard", 
# # #             "Agent 1: GDP Ranker", 
# # #             "Agent 2: City Segmenter", 
# # #             "Agent 3: Zone Finder", 
# # #             "Agent 4: Subarea Mapper", 
# # #             "Agent 5: Supabase", 
# # #             "Agent 6: Scraper"
# # #         ]
# # #         st.session_state.page = st.radio("", menu, label_visibility="collapsed")

# # def render_sidebar():
# #     with st.sidebar:
# #         st.markdown("### ⚙️ Navigation")
# #         menu = [
# #             "Dashboard", 
# #             "Agent 1: GDP Ranker", 
# #             "Agent 2: City Segmenter", 
# #             "Agent 3: Zone Finder", 
# #             "Agent 4: Subarea Mapper", 
# #             "Agent 5: Supabase", 
# #             "Agent 6: Scraper"
# #         ]
# #         # FIX: Changed "" to "Hidden Navigation" to satisfy Streamlit's accessibility rules
# #         st.session_state.page = st.radio("Hidden Navigation", menu, label_visibility="collapsed")

# # def render_execute_card():
# #     st.markdown('''<div class="card red-accent">
# #         <div class="card-header">
# #             <span>🚀 Execute Pipeline</span>
# #         </div>''', unsafe_allow_html=True)
    
# #     c1, c2, c3 = st.columns([3, 3, 2])
# #     with c1:
# #         mode = st.selectbox("Mode", ["Full Pipeline", "Direct Countries", "Direct Cities", "Direct Zones"])
# #     with c2:
# #         if mode == "Full Pipeline": param = st.text_input("Top N Countries", value="10")
# #         elif mode == "Direct Countries": param = st.text_input("Countries (comma-sep)", placeholder="India, UAE")
# #         elif mode == "Direct Cities": param = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi")
# #         else: param = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra")
        
# #     with c3:
# #         st.write("<div style='height:28px'></div>", unsafe_allow_html=True)
# #         run_btn = st.button("▶ Run Agent 1", disabled=st.session_state.pipeline_running, type="primary", use_container_width=True)
        
# #         if run_btn:
# #             st.session_state.pipeline_state = PipelineState()
# #             st.session_state.pipeline_done = False
# #             st.session_state.pipeline_error = False
# #             st.session_state.output_file = None
# #             st.session_state.agent_status = {1:"Pending", 2:"Pending", 3:"Pending", 4:"Pending", 4.5:"Pending", 5:"Pending", 5.5:"Pending"}
            
# #             cfg = {
# #                 "top_n": int(param) if mode == "Full Pipeline" and param.isdigit() else None,
# #                 "countries": param if mode == "Direct Countries" else (param if mode == "Direct Zones" else None),
# #                 "cities": param if mode in ["Direct Cities", "Direct Zones"] else None,
# #                 "zones": param if mode == "Direct Zones" else None,
# #                 "skip_supabase": True
# #             }
# #             # TO THIS:
# #             st.session_state.pipeline_running = True
# #             # Pass the actual PipelineState object to the thread so it doesn't touch session_state
# #             threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.pipeline_state, st.session_state.agent_status), daemon=True).start()

# #     if st.session_state.pipeline_running:
# #         st.info("⏳ Pipeline is running in background. View status below.")
# #     elif st.session_state.pipeline_error:
# #         st.error(f"❌ Failed: {st.session_state.pipeline_error}")
        
# #     st.markdown('</div>', unsafe_allow_html=True)

# # def render_data_explorer():
# #     st.markdown('''<div class="card">
# #         <div class="card-header"><span>📂 Select & View Data</span></div>''', unsafe_allow_html=True)
    
# #     state = st.session_state.pipeline_state
    
# #     # Extract lists safely
# #     countries = sorted(list(set([c.get("country") for c in state.all_cities])))
    
# #     # Create 4 columns for Select/View pairs
# #     col_c_sel, col_c_view, col_ci_sel, col_ci_view = st.columns(4)
    
# #     with col_c_sel:
# #         sel_country = st.selectbox("Select Country", ["--"] + countries)
# #     with col_c_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If country not available, execute Agent 1</div>", unsafe_allow_html=True)
        
# #     # Filter cities based on selected country
# #     filtered_cities = []
# #     if sel_country != "--":
# #         filtered_cities = sorted([c.get("city") for c in state.all_cities if c.get("country") == sel_country])
        
# #     with col_ci_sel:
# #         sel_city = st.selectbox("Select City", ["--"] + filtered_cities)
# #     with col_ci_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If city not available, execute Agent 2</div>", unsafe_allow_html=True)

# #     # Row 2: Zones and Subareas
# #     col_z_sel, col_z_view, col_sa_sel, col_sa_view = st.columns(4)
    
# #     filtered_zones = []
# #     if sel_city != "--" and sel_country != "--":
# #         filtered_zones = state.master_zone_registry.get((sel_city, sel_country), [])
        
# #     with col_z_sel:
# #         sel_zone = st.selectbox("Select Zone", ["--"] + filtered_zones)
# #     with col_z_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If zone not available, execute Agent 3</div>", unsafe_allow_html=True)
        
# #     filtered_subareas = []
# #     if sel_zone != "--" and sel_city != "--" and sel_country != "--":
# #         sa_list = state.master_subarea_registry.get((sel_zone, sel_city, sel_country), [])
# #         filtered_subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

# #     with col_sa_sel:
# #         sel_subarea = st.selectbox("Select Subarea", ["--"] + filtered_subareas)
# #     with col_sa_view:
# #         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If subarea not available, execute Agent 4</div>", unsafe_allow_html=True)

# #     st.markdown('</div>', unsafe_allow_html=True)
# #     return sel_country, sel_city, sel_zone, sel_subarea

# # def render_bottom_section(sel_country, sel_city, sel_zone, sel_subarea):
# #     status_col, table_col = st.columns([1, 2.5])
    
# #     # LEFT: Agent Status
# #     with status_col:
# #         st.markdown('''<div class="card">
# #             <div class="card-header"><span>📊 Status</span></div>''', unsafe_allow_html=True)
            
# #         agents = [
# #             (1, "GDP Ranker"), (2, "City Segmenter"), (3, "Zone Finder"),
# #             (4, "Subarea Mapper"), (5, "Company Scraper")
# #         ]
# #         for num, name in agents:
# #             status = st.session_state.agent_status.get(num, "Pending")
# #             cls = "agent-chip"
# #             if status == "Running": cls += " agent-running"
# #             elif status == "Done": cls += " agent-done"
# #             elif status == "Error": cls += " agent-error"
            
# #             icon = {"Pending": "⏸", "Running": "⏳", "Done": "✅", "Skipped": "⏭", "Error": "❌"}.get(status, "")
# #             st.markdown(f'<div class="{cls}">{icon} Agent {num} is {status}</div>', unsafe_allow_html=True)
            
# #         st.markdown('</div>', unsafe_allow_html=True)

# #     # RIGHT: Results Table
# #     with table_col:
# #         st.markdown('''<div class="card">
# #             <div class="card-header">
# #                 <span>🏢 Resultant Company Data</span>
# #             </div>''', unsafe_allow_html=True)
        
# #         companies = st.session_state.pipeline_state.scraped_companies
        
# #         # Dynamic Filtering based on selection
# #         if sel_subarea != "--":
# #             companies = [c for c in companies if c.get("subarea_name") == sel_subarea]
# #         elif sel_zone != "--":
# #             companies = [c for c in companies if c.get("zone_name") == sel_zone]
# #         elif sel_city != "--":
# #             companies = [c for c in companies if c.get("city_name") == sel_city]
# #         elif sel_country != "--":
# #             companies = [c for c in companies if c.get("country_name") == sel_country]

# #         if companies:
# #             df = pd.DataFrame(companies)
# #             # Ensure standard columns exist for clean viewing
# #             standard_cols = ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name", "country_name"]
# #             existing_cols = [c for c in standard_cols if c in df.columns]
# #             st.dataframe(df[existing_cols].reset_index(drop=True), use_container_width=True, height=300)
            
# #             if st.session_state.output_file and os.path.exists(st.session_state.output_file):
# #                 with open(st.session_state.output_file, "rb") as f:
# #                     st.download_button("⬇ Download Full Results JSON", f, file_name="leads_results.json")
# #         else:
# #             if st.session_state.pipeline_done:
# #                 st.info("No companies found for this specific filter.")
# #             else:
# #                 st.warning("Company data will appear here in a table format after executing the pipeline.")
                
# #         st.markdown('</div>', unsafe_allow_html=True)


# # # ── Main App Assembly ───────────────────────────────────────

# # render_header()
# # render_sidebar()

# # if st.session_state.page == "Dashboard":
# #     render_execute_card()
# #     sel_c, sel_ci, sel_z, sel_sa = render_data_explorer()
# #     render_bottom_section(sel_c, sel_ci, sel_z, sel_sa)
# # else:
# #     # Fallback for individual agent pages clicked in sidebar
# #     st.markdown(f'''
# #         <div class="card">
# #             <div class="card-header"><span>{st.session_state.page}</span></div>
# #             <p>Specific configurations and logs for this agent will be integrated here.</p>
# #             <p>To run the full sequential workflow, please navigate back to <b>Dashboard</b> and click "Run Agent 1".</p>
# #         </div>
# #     ''', unsafe_allow_html=True)

# # # Trigger UI refresh while pipeline is running in background
# # if st.session_state.pipeline_running:
# #     time.sleep(1)
# #     st.rerun()


# # ----------------------------------------------------------------------------------------------


# """
# ui_app.py — OxiqAI Lead Generation Agent Dashboard
# Exact prototype implementation: Header, Sidebar, Execute Pipeline, 
# Data Explorer, Agent Status, and Results Table.
# """

# import streamlit as st
# import threading
# import time
# import os
# import sys
# import json
# import pandas as pd
# from datetime import datetime
# from argparse import Namespace

# # ── Path setup ──────────────────────────────────────────────
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# sys.path.insert(0, BASE_DIR)

# import run_pipeline
# from run_pipeline import (
#     phase_1_gdp_ranking,
#     phase_2_city_segmentation,
#     phase_3_zone_finding,
#     phase_4_subarea_mapper,
#     phase_4_5_supabase_insert,
#     phase_5_lead_scraper,
#     phase_5_5_supabase_insert_leads,
# )
# from orchestrator_utils import PipelineState

# PROJECT_ROOT = run_pipeline.project_root

# # ── Page config ─────────────────────────────────────────────
# st.set_page_config(
#     page_title="OxiqAI Lead Generation Agent",
#     page_icon="🧠",
#     layout="wide",
#     initial_sidebar_state="expanded"
# )

# # ── Prototype CSS ───────────────────────────────────────────
# # st.markdown("""<style>
# #     /* Remove default Streamlit spacing */
# #     .block-container { padding-top: 0rem; padding-bottom: 2rem; }
# #     div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[style*="flex-direction: row"] { margin-top: -1rem; }
    
# #     /* Top Header Bar */
# #     .main-header {
# #         display: flex; align-items: center; justify-content: space-between;
# #         padding: 12px 30px; background-color: #0f172a; color: white;
# #         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
# #         border-radius: 0 0 10px 10px;
# #     }
# #     .header-left { display: flex; align-items: center; gap: 15px; }
# #     .header-logo { font-size: 36px; }
# #     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
# #     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
# #     .header-stage {
# #         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
# #         font-size: 14px; font-weight: 600; color: white;
# #     }

    
# #         /* Sidebar Styling */
# #     section[data-testid="stSidebar"] {
# #         background-color: #f8fafc; border-right: 1px solid #e2e8f0;
# #     }
    
# #     /* FORCE unselected text to be black */
# #     section[data-testid="stSidebar"] .stRadio p {
# #         color: #000000 !important;
# #         font-weight: 500 !important;
# #     }

# #     /* FORCE selected text to stay white on the blue background */
# #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] p {
# #         color: #ffffff !important;
# #         font-weight: bold !important;
# #     }

# #     /* Selected blue background styling */
# #     section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
# #         background-color: #2563eb !important; 
# #         border-radius: 8px; padding: 12px !important;
# #         box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
# #     }
    
# #     /* General spacing */
# #     section[data-testid="stSidebar"] .stRadio label {
# #         padding: 10px 12px !important; border-radius: 8px; margin-bottom: 4px;
# #     }

# #     /* Cards */
# #     .card {
# #         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
# #         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
# #     }
# #     .card-header {
# #         font-size: 16px; font-weight: 700; color: #0f172a; 
# #         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
# #         display: flex; justify-content: space-between; align-items: center;
# #     }
# #     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

# #     /* Agent Status Chips */
# #     .agent-chip {
# #         display: flex; align-items: center; padding: 10px 15px;
# #         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
# #         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
# #     }
# #     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
# #     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
# #     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
# #     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

# #     /* Data Viewers styling */
# #     .viewer-box {
# #         background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
# #         padding: 10px; min-height: 150px; max-height: 300px; overflow-y: auto;
# #         font-size: 14px; color: #334155;
# #     }
# # </style>""", unsafe_allow_html=True)

# st.markdown("""<style>
#     /* 1. FIX: Pull the top header down so it doesn't get cut off */
#     .block-container { 
#         padding-top: 1rem; 
#         padding-bottom: 2rem; 
#     }
#     .main-header {
#         margin-top: 30px; /* Drags header up into the empty space safely */
#     }

#     /* 2. Top Header Bar Styling */
#     .main-header {
#         display: flex; align-items: center; justify-content: space-between;
#         padding: 15px 30px; background-color: #0f172a; color: white;
#         border-bottom: 4px solid #2563eb; margin-bottom: 25px;
#         border-radius: 0 0 10px 10px;
#     }
#     .header-left { display: flex; align-items: center; gap: 15px; }
#     .header-logo { font-size: 36px; }
#     .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
#     .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
#     .header-stage {
#         background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
#         font-size: 14px; font-weight: 600; color: white;
#     }

#         /* 3. FORCE Sidebar Background Color (targets nested divs) */
#     section[data-testid="stSidebar"] {
#         background-color: #eef2ff !important; /* Very light blue shade */
#     }
#     section[data-testid="stSidebar"] > div {
#         background-color: #eef2ff !important; /* Forces color on inner wrapper */
#     }
#     [data-testid="stSidebarContent"] {
#         background-color: #eef2ff !important; /* Forces color on content area */
#     }

#     /* 4. FORCE Sidebar Toggle Button to ALWAYS be visible */
#     button[data-testid="stSidebarCollapseButton"] {
#         visibility: visible !important;
#         opacity: 1 !important;
#         background-color: #cbd5e1 !important; /* Gives it a light grey background so you can see it */
#         box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
#     }
#     /* Fallback for older Streamlit versions */
#     [data-testid="stSidebarCollapsedControl"] {
#         visibility: visible !important;
#         opacity: 1 !important;
#     }

#     /* 5. Force everything black text */
#     section[data-testid="stSidebar"] * {
#         color: #000000 !important; 
#     }
    
    

#     /* 6. Cards */
#     .card {
#         background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
#         padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
#     }
#     .agent-text { color: #000000 !important; font-size: 15px; line-height: 1.6; }
#     .card-header {
#         font-size: 16px; font-weight: 700; color: #0f172a; 
#         border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
#         display: flex; justify-content: space-between; align-items: center;
#     }
#     .red-accent { border-left: 5px solid #ef4444; padding-left: 15px; }

#     /* 7. Agent Status Chips */
#     .agent-chip {
#         display: flex; align-items: center; padding: 10px 15px;
#         border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 14px;
#         background-color: #f1f5f9; color: #64748b; border-left: 4px solid #cbd5e1;
#     }
#     .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; animation: pulse 1.5s infinite; }
#     .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
#     .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
    
#     @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

#     # ------------------------------------
#         /* --- NUCLEAR SIDEBAR BACKGROUND FIX --- */
#     [data-testid="stSidebar"],
#     [data-testid="stSidebar"] > div,
#     [data-testid="stSidebar"] > div > div,
#     [data-testid="stSidebarContent"] {
#         background-color: #e0e7ff !important; /* Soft light blue shade */
#     }

#     /* --- NUCLEAR TOGGLE BUTTON FIX --- */
#     /* Targets the button OUTSIDE the sidebar container */
#     [data-testid="stSidebarCollapseButton"],
#     button[kind="header"] {
#         visibility: visible !important;
#         opacity: 1 !important;
#         background-color: rgba(255, 255, 255, 0.95) !important;
#         border: 1px solid #cbd5e1 !important;
#         box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
#         border-radius: 8px !important;
#         transition: all 0.2s ease !important;
#     }
    
#     /* Make the button pop out slightly on hover */
#     [data-testid="stSidebarCollapseButton"]:hover,
#     button[kind="header"]:hover {
#         background-color: #ffffff !important;
#         transform: scale(1.1) !important;
#         box-shadow: 0 4px 10px rgba(0,0,0,0.2) !important;
#     }
# </style>        

#             """, unsafe_allow_html=True)


# # ── Session State Init ──────────────────────────────────────
# def init_session_state():
#     defaults = {
#         "page": "Dashboard",
#         "pipeline_running": False,
#         "pipeline_done": False,
#         "pipeline_error": False,
#         "pipeline_state": PipelineState(),
#         "agent_status": {
#             1: "Pending", 2: "Pending", 3: "Pending", 
#             4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"
#         },
#         "output_file": None
#     }
#     for key, val in defaults.items():
#         if key not in st.session_state:
#             st.session_state[key] = val

# init_session_state()


# # ── Pipeline Thread ─────────────────────────────────────────
# def pipeline_worker(config: dict, state: PipelineState, agent_status: dict):
#     args = Namespace(
#         countries=config.get("countries") or None,
#         top_n=config.get("top_n") or None,
#         refresh_gdp=config.get("refresh_gdp", False),
#         cities=config.get("cities") or None,
#         zones=config.get("zones") or None,
#         max_scrolls=config.get("max_scrolls", 8),
#         max_scrapers=config.get("max_scrapers", 3),
#         skip_supabase=config.get("skip_supabase", True),
#     )

#     def mark(num, status): agent_status[num] = status

#     try:
#         if args.zones:
#             mark(1, "Skipped"); mark(2, "Skipped"); mark(3, "Skipped")
#             dz = [z.strip() for z in args.zones.split(",") if z.strip()]
#             city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
#             country = args.countries.split(",")[0].strip() if args.countries else "India"
#             state.master_zone_registry[(city, country)] = dz
#             state.all_cities.append({"city": city, "country": country, "tier": 1})

#         elif args.cities:
#             mark(1, "Skipped"); mark(2, "Skipped")
#             cities = [c.strip() for c in args.cities.split(",") if c.strip()]
#             country = args.countries.split(",")[0].strip() if args.countries else "India"
#             for cn in cities: state.all_cities.append({"city": cn, "country": country, "tier": 1})
            
#             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

#         else:
#             mark(1, "Running"); phase_1_gdp_ranking(state, args); mark(1, "Done")
#             mark(2, "Running"); phase_2_city_segmentation(state); mark(2, "Done")
#             if not state.all_cities: raise Exception("No cities found after Phase 2.")
#             mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

#         if not state.master_zone_registry: raise Exception("No zones found.")
        
#         mark(4, "Running"); phase_4_subarea_mapper(state); mark(4, "Done")
        
#         if args.skip_supabase: mark(4.5, "Skipped")
#         else: mark(4.5, "Running"); phase_4_5_supabase_insert(state, args.skip_supabase); mark(4.5, "Done")
        
#         mark(5, "Running"); phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers); mark(5, "Done")
        
#         if args.skip_supabase: mark(5.5, "Skipped")
#         else: mark(5.5, "Running"); phase_5_5_supabase_insert_leads(state, args.skip_supabase); mark(5.5, "Done")

#         state.finalize()
#         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
#         out_dir = os.path.join(PROJECT_ROOT, "outputs")
#         os.makedirs(out_dir, exist_ok=True)
#         out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
#         with open(out_file, "w", encoding="utf-8") as f:
#             json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
        
#         st.session_state.output_file = out_file
#         st.session_state.pipeline_done = True

#     except Exception as e:
#         for k, v in agent_status.items():
#             if v == "Running": agent_status[k] = "Error"
#     finally:
#         st.session_state.pipeline_running = False


# # ── UI Components ───────────────────────────────────────────

# def render_header():
#     st.markdown('''
#         <div class="main-header">
#             <div class="header-left">
#                 <div class="header-logo">🧠</div>
#                 <div class="header-title">
#                     <h1>OxiqAI Lead Generation Agent</h1>
#                     <p>Automated B2B Database Preparation & Enrichment</p>
#                 </div>
#             </div>
#             <div class="header-stage">Stage 1: Active DB Preparation</div>
#         </div>
#     ''', unsafe_allow_html=True)

# def render_sidebar():
#     with st.sidebar:
#         # ── Add Logo ────────────────────────────────────────
#         logo_path = os.path.join(BASE_DIR, "logo.png")
#         if os.path.exists(logo_path):
#             # Use st.image for the local file
#             st.image(logo_path, width=150, use_container_width=False)
#         else:
#             # Fallback URL if you haven't downloaded it yet
#             st.markdown(
#                 '<img src="https://z-cdn-media.chatglm.cn/files/c826e954-a835-4fec-a43f-fc63b4c75512.png?auth_key=1882483990-5ef1ebd9e9354e739be90892f649eb4c-0-ed68ad389658a2f65557a8659a9d4321" style="width: 150px; display: block; margin: 0 auto 15px auto; border-radius: 8px;">', 
#                 unsafe_allow_html=True
#             )
        
#         # Add a little space under the logo
#         st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

#         st.markdown("### ⚙️ Navigation")
#         menu = [
#             "Dashboard", 
#             "Agent 1: GDP Ranker", 
#             "Agent 2: City Segmenter", 
#             "Agent 3: Zone Finder", 
#             "Agent 4: Subarea Mapper", 
#             "Agent 5: Supabase", 
#             "Agent 6: Scraper"
#         ]
#         st.session_state.page = st.radio("Hidden Navigation", menu, label_visibility="collapsed")

# def render_execute_card():
#     st.markdown('''<div class="card red-accent">
#         <div class="card-header">
#             <span>🚀 Execute Pipeline</span>
#         </div>''', unsafe_allow_html=True)
    
#     c1, c2, c3 = st.columns([3, 3, 2])
#     with c1:
#         mode = st.selectbox("Mode", ["Full Pipeline", "Direct Countries", "Direct Cities", "Direct Zones"])
#     with c2:
#         if mode == "Full Pipeline": param = st.text_input("Top N Countries", value="10")
#         elif mode == "Direct Countries": param = st.text_input("Countries (comma-sep)", placeholder="India, UAE")
#         elif mode == "Direct Cities": param = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi")
#         else: param = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra")
        
#     with c3:
#         st.write("<div style='height:28px'></div>", unsafe_allow_html=True)
#         run_btn = st.button("▶ Run Agent 1", disabled=st.session_state.pipeline_running, type="primary", width="stretch")
        
#         if run_btn:
#             st.session_state.pipeline_state = PipelineState()
#             st.session_state.pipeline_done = False
#             st.session_state.pipeline_error = False
#             st.session_state.output_file = None
#             st.session_state.agent_status = {1:"Pending", 2:"Pending", 3:"Pending", 4:"Pending", 4.5:"Pending", 5:"Pending", 5.5:"Pending"}
            
#             cfg = {
#                 "top_n": int(param) if mode == "Full Pipeline" and param.isdigit() else None,
#                 "countries": param if mode == "Direct Countries" else (param if mode == "Direct Zones" else None),
#                 "cities": param if mode in ["Direct Cities", "Direct Zones"] else None,
#                 "zones": param if mode == "Direct Zones" else None,
#                 "skip_supabase": True
#             }
#             st.session_state.pipeline_running = True
#             # Pass the actual PipelineState object to the thread so it doesn't touch session_state
#             threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.pipeline_state, st.session_state.agent_status), daemon=True).start()

#     if st.session_state.pipeline_running:
#         st.info("⏳ Pipeline is running in background. View status below.")
#     elif st.session_state.pipeline_error:
#         st.error(f"❌ Failed: {st.session_state.pipeline_error}")
        
#     st.markdown('</div>', unsafe_allow_html=True)

# def render_data_explorer():
#     st.markdown('''<div class="card">
#         <div class="card-header"><span>📂 Select & View Data</span></div>''', unsafe_allow_html=True)
    
#     state = st.session_state.pipeline_state
    
#     # Extract lists safely
#     countries = sorted(list(set([c.get("country") for c in state.all_cities])))
    
#     # Create 4 columns for Select/View pairs
#     col_c_sel, col_c_view, col_ci_sel, col_ci_view = st.columns(4)
    
#     with col_c_sel:
#         sel_country = st.selectbox("Select Country", ["--"] + countries)
#     with col_c_view:
#         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If country not available, execute Agent 1</div>", unsafe_allow_html=True)
        
#     # Filter cities based on selected country
#     filtered_cities = []
#     if sel_country != "--":
#         filtered_cities = sorted([c.get("city") for c in state.all_cities if c.get("country") == sel_country])
        
#     with col_ci_sel:
#         sel_city = st.selectbox("Select City", ["--"] + filtered_cities)
#     with col_ci_view:
#         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If city not available, execute Agent 2</div>", unsafe_allow_html=True)

#     # Row 2: Zones and Subareas
#     col_z_sel, col_z_view, col_sa_sel, col_sa_view = st.columns(4)
    
#     filtered_zones = []
#     if sel_city != "--" and sel_country != "--":
#         filtered_zones = state.master_zone_registry.get((sel_city, sel_country), [])
        
#     with col_z_sel:
#         sel_zone = st.selectbox("Select Zone", ["--"] + filtered_zones)
#     with col_z_view:
#         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If zone not available, execute Agent 3</div>", unsafe_allow_html=True)
        
#     filtered_subareas = []
#     if sel_zone != "--" and sel_city != "--" and sel_country != "--":
#         sa_list = state.master_subarea_registry.get((sel_zone, sel_city, sel_country), [])
#         filtered_subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

#     with col_sa_sel:
#         sel_subarea = st.selectbox("Select Subarea", ["--"] + filtered_subareas)
#     with col_sa_view:
#         st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If subarea not available, execute Agent 4</div>", unsafe_allow_html=True)

#     st.markdown('</div>', unsafe_allow_html=True)
#     return sel_country, sel_city, sel_zone, sel_subarea

# def render_bottom_section(sel_country, sel_city, sel_zone, sel_subarea):
#     status_col, table_col = st.columns([1, 2.5])
    
#     # LEFT: Agent Status
#     with status_col:
#         st.markdown('''<div class="card">
#             <div class="card-header"><span>📊 Status</span></div>''', unsafe_allow_html=True)
            
#         agents = [
#             (1, "GDP Ranker"), (2, "City Segmenter"), (3, "Zone Finder"),
#             (4, "Subarea Mapper"), (5, "Company Scraper")
#         ]
#         for num, name in agents:
#             status = st.session_state.agent_status.get(num, "Pending")
#             cls = "agent-chip"
#             if status == "Running": cls += " agent-running"
#             elif status == "Done": cls += " agent-done"
#             elif status == "Error": cls += " agent-error"
            
#             icon = {"Pending": "⏸", "Running": "⏳", "Done": "✅", "Skipped": "⏭", "Error": "❌"}.get(status, "")
#             st.markdown(f'<div class="{cls}">{icon} Agent {num} is {status}</div>', unsafe_allow_html=True)
            
#         st.markdown('</div>', unsafe_allow_html=True)

#     # RIGHT: Results Table
#     with table_col:
#         st.markdown('''<div class="card">
#             <div class="card-header">
#                 <span>🏢 Resultant Company Data</span>
#             </div>''', unsafe_allow_html=True)
        
#         companies = st.session_state.pipeline_state.scraped_companies
        
#         # Dynamic Filtering based on selection
#         if sel_subarea != "--":
#             companies = [c for c in companies if c.get("subarea_name") == sel_subarea]
#         elif sel_zone != "--":
#             companies = [c for c in companies if c.get("zone_name") == sel_zone]
#         elif sel_city != "--":
#             companies = [c for c in companies if c.get("city_name") == sel_city]
#         elif sel_country != "--":
#             companies = [c for c in companies if c.get("country_name") == sel_country]

#         if companies:
#             df = pd.DataFrame(companies)
#             # Ensure standard columns exist for clean viewing
#             standard_cols = ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name", "country_name"]
#             existing_cols = [c for c in standard_cols if c in df.columns]
#             st.dataframe(df[existing_cols].reset_index(drop=True), width="stretch", height=300)
            
#             if st.session_state.output_file and os.path.exists(st.session_state.output_file):
#                 with open(st.session_state.output_file, "rb") as f:
#                     st.download_button("⬇ Download Full Results JSON", f, file_name="leads_results.json")
#         else:
#             if st.session_state.pipeline_done:
#                 st.info("No companies found for this specific filter.")
#             else:
#                 st.warning("Company data will appear here in a table format after executing the pipeline.")
                
#         st.markdown('</div>', unsafe_allow_html=True)


# # ----------------------Individual Page Results--------------------------------------

# # ── Render Individual Agent Pages ──────────────────────────
# def render_agent_page(page_name):
#     state = st.session_state.pipeline_state
    
#     # Determine agent number for status badge
#     status_map = {"Agent 1": 1, "Agent 2": 2, "Agent 3": 3, "Agent 4": 4, "Agent 5": 4.5, "Agent 6": 5}
#     agent_num = next((num for name, num in status_map.items() if name in page_name), None)
#     agent_status = st.session_state.agent_status.get(agent_num, "Pending") if agent_num else "Unknown"
    
#     # Render Header Card with forced black text
#     st.markdown(f'''
#         <div class="card">
#             <div class="card-header">
#                 <span class="agent-text">{page_name}</span>
#                 <span style="background:#f1f5f9; color:#000; padding:5px 12px; border-radius:8px; font-weight:600; font-size:13px;">
#                     Status: {agent_status}
#                 </span>
#             </div>
#         </div>
#     ''', unsafe_allow_html=True)

#     # Render Results based on which agent was clicked
#     if "Agent 1" in page_name:
#         data = state.gdp_ranked_countries
#         if data:
#             st.dataframe(pd.DataFrame(data), width="stretch")
#         else:
#             st.markdown('<p class="agent-text">No GDP data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

#     elif "Agent 2" in page_name:
#         data = state.all_cities
#         if data:
#             st.dataframe(pd.DataFrame(data), width="stretch")
#         else:
#             st.markdown('<p class="agent-text">No city data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

#     elif "Agent 3" in page_name:
#         # Flatten the zone registry dictionary into a table format
#         zone_rows = []
#         for (city, country), zones in state.master_zone_registry.items():
#             for z in zones:
#                 zone_rows.append({"Country": country, "City": city, "Zone Name": z})
#         if zone_rows:
#             st.dataframe(pd.DataFrame(zone_rows), width="stretch")
#         else:
#             st.markdown('<p class="agent-text">No zone data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

#     elif "Agent 4" in page_name:
#         data = state.all_subarea_rows
#         if data:
#             # Select common columns to keep the table clean
#             cols = [c for c in ["zone_name", "subarea_name", "city", "country", "business_volume", "status"] if c in data[0]]
#             st.dataframe(pd.DataFrame(data)[cols], width="stretch")
#         else:
#             st.markdown('<p class="agent-text">No sub-area data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

#     elif "Agent 5" in page_name:
#         st.markdown('<p class="agent-text">Supabase insertion status.</p>', unsafe_allow_html=True)
#         st.markdown(f'<p class="agent-text"><b>Subareas Insert:</b> {st.session_state.agent_status.get(4.5, "Pending")}</p>', unsafe_allow_html=True)
#         st.markdown(f'<p class="agent-text"><b>Leads Insert:</b> {st.session_state.agent_status.get(5.5, "Pending")}</p>', unsafe_allow_html=True)

#     elif "Agent 6" in page_name:
#         data = state.scraped_companies
#         if data:
#             cols = [c for c in ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name"] if c in data[0]]
#             st.dataframe(pd.DataFrame(data)[cols], width="stretch")
#         else:
#             st.markdown('<p class="agent-text">No scraped company data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# # ── Main App Assembly ───────────────────────────────────────

# render_header()
# render_sidebar()

# if st.session_state.page == "Dashboard":
#     render_execute_card()
#     sel_c, sel_ci, sel_z, sel_sa = render_data_explorer()
#     render_bottom_section(sel_c, sel_ci, sel_z, sel_sa)
# # else:
# #     # Fallback for individual agent pages clicked in sidebar
# #     st.markdown(f'''
# #         <div class="card">
# #             <div class="card-header"><span>{st.session_state.page}</span></div>
# #             <p>Specific configurations and logs for this agent will be integrated here.</p>
# #             <p>To run the full sequential workflow, please navigate back to <b>Dashboard</b> and click "Run Agent 1".</p>
# #         </div>
# #     ''', unsafe_allow_html=True)
# else:
#     # Show individual agent data
#     render_agent_page(st.session_state.page)

# # Trigger UI refresh while pipeline is running in background
# if st.session_state.pipeline_running:
#     time.sleep(1)
#     st.rerun()

# --------------------------------------------------------------------------------------------


"""
ui_app.py — OxiqAI Lead Generation Agent Dashboard
Professional UI implementation: Header, Sidebar, Execute Pipeline, 
Data Explorer, Agent Status, and Results Table.
"""

import streamlit as st
import threading
import time
import os
import sys
import json
import pandas as pd
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
    page_title="OxiqAI Lead Generation Agent",
    page_icon=" ",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Professional CSS ───────────────────────────────────────
st.markdown("""<style>
    /* Layout Spacing */
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    .main-header { margin-top: 30px; }

    /* Top Header Bar */
    .main-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 15px 30px; background-color: #0f172a; color: white;
        border-bottom: 4px solid #2563eb; margin-bottom: 25px;
        border-radius: 0 0 10px 10px;
    }
    .header-left { display: flex; align-items: center; gap: 15px; }
    .header-title h1 { margin: 0; font-size: 24px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; }
    .header-title p { margin: 0; color: #94a3b8; font-size: 13px; font-weight: 500; }
    .header-stage {
        background-color: #2563eb; padding: 8px 20px; border-radius: 20px;
        font-size: 14px; font-weight: 600; color: white;
    }

    /* Sidebar Base Background (Clean Professional Off-White) */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] > div > div,
    [data-testid="stSidebarContent"] {
        background-color: #0282fa !important; 
    }

    /* Toggle Button */
    [data-testid="stSidebarCollapseButton"],
    button[kind="header"] {
        visibility: visible !important; opacity: 1 !important;
        background-color: rgba(255, 255, 255, 0.95) !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
        border-radius: 8px !important; transition: all 0.2s ease !important;
    }
    [data-testid="stSidebarCollapseButton"]:hover,
    button[kind="header"]:hover {
        background-color: #ffffff !important; transform: scale(1.1) !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2) !important;
    }

    /* Sidebar Text */
    section[data-testid="stSidebar"] * { color: #1e293b !important; }
    
    /* Menu Item Containers (Makes them look like cards) */
    section[data-testid="stSidebar"] .stRadio label {
        background-color: #ffffff; /* White card background */
        border: 1px solid #e2e8f0; /* Subtle border */
        border-radius: 8px; 
        padding: 12px 15px !important; 
        margin-bottom: 8px !important; /* Gap between items */
        box-shadow: 0 1px 3px rgba(0,0,0,0.04); /* Soft shadow */
        transition: all 0.2s ease-in-out;
        font-weight: 500;
    }
    
    /* Menu Item Hover Effect */
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: #f1f5f9; 
        border-color: #cbd5e1;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);
        transform: translateY(-1px);
    }

    /* Selected Menu Item */
    section[data-testid="stSidebar"] .stRadio [aria-checked="true"] > div {
        background-color: #2563eb !important; 
        border: 1px solid #2563eb !important; 
        border-radius: 8px; padding: 12px 15px !important;
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.25);
    }
    section[data-testid="stSidebar"] .stRadio [aria-checked="true"] * {
        color: #ffffff !important; font-weight: 600 !important;
    }

    /* Main Content Cards */
    .card {
        background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
        padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .agent-text { color: #0f172a !important; font-size: 15px; line-height: 1.6; }
    .card-header {
        font-size: 16px; font-weight: 700; color: #0f172a; 
        border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .slate-accent { border-left: 5px solid #334155; padding-left: 15px; }

    /* Agent Status Chips */
    .agent-chip {
        display: flex; align-items: center; padding: 10px 15px;
        border-radius: 8px; margin-bottom: 8px; font-weight: 600; font-size: 13px;
        background-color: #f8fafc; color: #64748b; border-left: 4px solid #cbd5e1;
        text-transform: uppercase; letter-spacing: 0.5px;
    }
    .agent-running { background-color: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; }
    .agent-done { background-color: #f0fdf4; color: #15803d; border-left-color: #22c55e; }
    .agent-error { background-color: #fef2f2; color: #b91c1c; border-left-color: #ef4444; }
</style>""", unsafe_allow_html=True)


# ── Session State Init ──────────────────────────────────────
def init_session_state():
    defaults = {
        "page": "Dashboard",
        "pipeline_running": False,
        "pipeline_done": False,
        "pipeline_error": False,
        "pipeline_state": PipelineState(),
        "agent_status": {
            1: "Pending", 2: "Pending", 3: "Pending", 
            4: "Pending", 4.5: "Pending", 5: "Pending", 5.5: "Pending"
        },
        "output_file": None
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()


# ── Pipeline Thread ─────────────────────────────────────────
def pipeline_worker(config: dict, state: PipelineState, agent_status: dict):
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

    def mark(num, status): agent_status[num] = status

    try:
        if args.zones:
            mark(1, "Skipped"); mark(2, "Skipped"); mark(3, "Skipped")
            dz = [z.strip() for z in args.zones.split(",") if z.strip()]
            city = args.cities.split(",")[0].strip() if args.cities else "Mumbai"
            country = args.countries.split(",")[0].strip() if args.countries else "India"
            state.master_zone_registry[(city, country)] = dz
            state.all_cities.append({"city": city, "country": country, "tier": 1})

        elif args.cities:
            mark(1, "Skipped"); mark(2, "Skipped")
            cities = [c.strip() for c in args.cities.split(",") if c.strip()]
            country = args.countries.split(",")[0].strip() if args.countries else "India"
            for cn in cities: state.all_cities.append({"city": cn, "country": country, "tier": 1})
            mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

        else:
            mark(1, "Running"); phase_1_gdp_ranking(state, args); mark(1, "Done")
            mark(2, "Running"); phase_2_city_segmentation(state); mark(2, "Done")
            if not state.all_cities: raise Exception("No cities found after Phase 2.")
            mark(3, "Running"); phase_3_zone_finding(state); mark(3, "Done")

        if not state.master_zone_registry: raise Exception("No zones found.")
        
        mark(4, "Running"); phase_4_subarea_mapper(state); mark(4, "Done")
        if args.skip_supabase: mark(4.5, "Skipped")
        else: mark(4.5, "Running"); phase_4_5_supabase_insert(state, args.skip_supabase); mark(4.5, "Done")
        
        mark(5, "Running"); phase_5_lead_scraper(state, args.max_scrolls, args.max_scrapers); mark(5, "Done")
        if args.skip_supabase: mark(5.5, "Skipped")
        else: mark(5.5, "Running"); phase_5_5_supabase_insert_leads(state, args.skip_supabase); mark(5.5, "Done")

        state.finalize()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(PROJECT_ROOT, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"pipeline_lead_results_{ts}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(state.scraped_companies, f, indent=4, ensure_ascii=False)
        
        st.session_state.output_file = out_file
        st.session_state.pipeline_done = True

    except Exception as e:
        for k, v in agent_status.items():
            if v == "Running": agent_status[k] = "Error"
    finally:
        st.session_state.pipeline_running = False


# ── UI Components ───────────────────────────────────────────

def render_header():
    st.markdown('''
        <div class="main-header">
            <div class="header-left">
                <div class="header-title">
                    <h1>OxiqAI Lead Generation Agent</h1>
                    <p>Automated B2B Database Preparation & Enrichment</p>
                </div>
            </div>
            <div class="header-stage">Stage 1: Active DB Preparation</div>
        </div>
    ''', unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        # Inject specific sidebar styling for iframe
        st.markdown("""<style>
            [data-testid="stSidebarContent"], [data-testid="stSidebarContent"] > div { background-color: #0282fa !important; }
        </style>""", unsafe_allow_html=True)

        # ── Logo (Left Aligned, Larger Size) ────────────────
        logo_path = os.path.join(BASE_DIR, "logo.png")
        if os.path.exists(logo_path):
            st.markdown("<div style='margin-top: -20px;'></div>", unsafe_allow_html=True)
            st.image(logo_path, width=110)
        else:
            # Removed 'margin: 0 auto' to force left alignment
            st.markdown(
                '<img src="https://z-cdn-media.chatglm.cn/files/c826e954-a835-4fec-a43f-fc63b4c75512.png?auth_key=1882483990-5ef1ebd9e9354e739be90892f649eb4c-0-ed68ad389658a2f65557a8659a9d4321" style="width: 110px; margin-top: -20px; margin-bottom: 25px; border-radius: 8px;">', 
                unsafe_allow_html=True
            )
        
        # Navigation Title
        st.markdown("<h3 style='margin-bottom:12px; color:#0f172a; font-size:20px; text-transform:uppercase; letter-spacing:1px;'>Navigation</h3>", unsafe_allow_html=True)
        
        menu = [
            "Dashboard", 
            "Agent 1: GDP Ranker", 
            "Agent 2: City Segmenter", 
            "Agent 3: Zone Finder", 
            "Agent 4: Subarea Mapper", 
            "Agent 5: Supabase", 
            "Agent 6: Scraper"
        ]
        st.session_state.page = st.radio("Hidden Navigation", menu, label_visibility="collapsed")

def render_execute_card():
    st.markdown('''<div class="card slate-accent">
        <div class="card-header">
            <span>Execute Pipeline</span>
        </div>''', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([3, 3, 2])
    with c1:
        mode = st.selectbox("Mode", ["Full Pipeline", "Direct Countries", "Direct Cities", "Direct Zones"])
    with c2:
        if mode == "Full Pipeline": param = st.text_input("Top N Countries", value="10")
        elif mode == "Direct Countries": param = st.text_input("Countries (comma-sep)", placeholder="India, UAE")
        elif mode == "Direct Cities": param = st.text_input("Cities (comma-sep)", placeholder="Mumbai, Delhi")
        else: param = st.text_input("Zones (comma-sep)", placeholder="Andheri, Bandra")
        
    with c3:
        st.write("<div style='height:28px'></div>", unsafe_allow_html=True)
        run_btn = st.button("Run Agent", disabled=st.session_state.pipeline_running, type="primary", width="stretch")
        
        if run_btn:
            st.session_state.pipeline_state = PipelineState()
            st.session_state.pipeline_done = False
            st.session_state.pipeline_error = False
            st.session_state.output_file = None
            st.session_state.agent_status = {1:"Pending", 2:"Pending", 3:"Pending", 4:"Pending", 4.5:"Pending", 5:"Pending", 5.5:"Pending"}
            
            cfg = {
                "top_n": int(param) if mode == "Full Pipeline" and param.isdigit() else None,
                "countries": param if mode == "Direct Countries" else (param if mode == "Direct Zones" else None),
                "cities": param if mode in ["Direct Cities", "Direct Zones"] else None,
                "zones": param if mode == "Direct Zones" else None,
                "skip_supabase": True
            }
            st.session_state.pipeline_running = True
            threading.Thread(target=pipeline_worker, args=(cfg, st.session_state.pipeline_state, st.session_state.agent_status), daemon=True).start()

    if st.session_state.pipeline_running:
        st.info("Pipeline is running in the background. View status below.")
    elif st.session_state.pipeline_error:
        st.error(f"Failed: {st.session_state.pipeline_error}")
        
    st.markdown('</div>', unsafe_allow_html=True)

def render_data_explorer():
    st.markdown('''<div class="card">
        <div class="card-header"><span>Select & View Data</span></div>''', unsafe_allow_html=True)
    
    state = st.session_state.pipeline_state
    countries = sorted(list(set([c.get("country") for c in state.all_cities])))
    
    col_c_sel, col_c_view, col_ci_sel, col_ci_view = st.columns(4)
    with col_c_sel:
        sel_country = st.selectbox("Select Country", ["--"] + countries)
    with col_c_view:
        st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If unavailable, execute Agent 1</div>", unsafe_allow_html=True)
        
    filtered_cities = []
    if sel_country != "--":
        filtered_cities = sorted([c.get("city") for c in state.all_cities if c.get("country") == sel_country])
        
    with col_ci_sel:
        sel_city = st.selectbox("Select City", ["--"] + filtered_cities)
    with col_ci_view:
        st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If unavailable, execute Agent 2</div>", unsafe_allow_html=True)

    col_z_sel, col_z_view, col_sa_sel, col_sa_view = st.columns(4)
    filtered_zones = []
    if sel_city != "--" and sel_country != "--":
        filtered_zones = state.master_zone_registry.get((sel_city, sel_country), [])
        
    with col_z_sel:
        sel_zone = st.selectbox("Select Zone", ["--"] + filtered_zones)
    with col_z_view:
        st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If unavailable, execute Agent 3</div>", unsafe_allow_html=True)
        
    filtered_subareas = []
    if sel_zone != "--" and sel_city != "--" and sel_country != "--":
        sa_list = state.master_subarea_registry.get((sel_zone, sel_city, sel_country), [])
        filtered_subareas = [sa.get("subarea_name") for sa in sa_list if sa.get("subarea_name")]

    with col_sa_sel:
        sel_subarea = st.selectbox("Select Subarea", ["--"] + filtered_subareas)
    with col_sa_view:
        st.markdown("<div style='padding-top:28px; font-size:13px; color:#64748b;'>If unavailable, execute Agent 4</div>", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
    return sel_country, sel_city, sel_zone, sel_subarea

def render_bottom_section(sel_country, sel_city, sel_zone, sel_subarea):
    status_col, table_col = st.columns([1, 2.5])
    
    with status_col:
        st.markdown('''<div class="card">
            <div class="card-header"><span>Agent Status</span></div>''', unsafe_allow_html=True)
            
        agents = [
            (1, "GDP Ranker"), (2, "City Segmenter"), (3, "Zone Finder"),
            (4, "Subarea Mapper"), (5, "Company Scraper")
        ]
        for num, name in agents:
            status = st.session_state.agent_status.get(num, "Pending")
            cls = "agent-chip"
            if status == "Running": cls += " agent-running"
            elif status == "Done": cls += " agent-done"
            elif status == "Error": cls += " agent-error"
            st.markdown(f'<div class="{cls}">Agent {num} - {status}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with table_col:
        st.markdown('''<div class="card">
            <div class="card-header"><span>Resultant Company Data</span></div>''', unsafe_allow_html=True)
        
        companies = st.session_state.pipeline_state.scraped_companies
        
        if sel_subarea != "--":
            companies = [c for c in companies if c.get("subarea_name") == sel_subarea]
        elif sel_zone != "--":
            companies = [c for c in companies if c.get("zone_name") == sel_zone]
        elif sel_city != "--":
            companies = [c for c in companies if c.get("city_name") == sel_city]
        elif sel_country != "--":
            companies = [c for c in companies if c.get("country_name") == sel_country]

        if companies:
            df = pd.DataFrame(companies)
            standard_cols = ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name", "country_name"]
            existing_cols = [c for c in standard_cols if c in df.columns]
            st.dataframe(df[existing_cols].reset_index(drop=True), width="stretch", height=300)
            
            if st.session_state.output_file and os.path.exists(st.session_state.output_file):
                with open(st.session_state.output_file, "rb") as f:
                    st.download_button("Download Full Results JSON", f, file_name="leads_results.json")
        else:
            if st.session_state.pipeline_done:
                st.info("No companies found for this specific filter.")
            else:
                st.warning("Company data will appear here in a table format after executing the pipeline.")
        st.markdown('</div>', unsafe_allow_html=True)

def render_agent_page(page_name):
    state = st.session_state.pipeline_state
    status_map = {"Agent 1": 1, "Agent 2": 2, "Agent 3": 3, "Agent 4": 4, "Agent 5": 4.5, "Agent 6": 5}
    agent_num = next((num for name, num in status_map.items() if name in page_name), None)
    agent_status = st.session_state.agent_status.get(agent_num, "Pending") if agent_num else "Unknown"
    
    st.markdown(f'''
        <div class="card">
            <div class="card-header">
                <span class="agent-text">{page_name}</span>
                <span style="background:#f1f5f9; color:#000; padding:5px 12px; border-radius:8px; font-weight:600; font-size:13px;">
                    Status: {agent_status}
                </span>
            </div>
        </div>
    ''', unsafe_allow_html=True)

    if "Agent 1" in page_name:
        data = state.gdp_ranked_countries
        if data: st.dataframe(pd.DataFrame(data), width="stretch")
        else: st.markdown('<p class="agent-text">No GDP data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)
    elif "Agent 2" in page_name:
        data = state.all_cities
        if data: st.dataframe(pd.DataFrame(data), width="stretch")
        else: st.markdown('<p class="agent-text">No city data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)
    elif "Agent 3" in page_name:
        zone_rows = []
        for (city, country), zones in state.master_zone_registry.items():
            for z in zones: zone_rows.append({"Country": country, "City": city, "Zone Name": z})
        if zone_rows: st.dataframe(pd.DataFrame(zone_rows), width="stretch")
        else: st.markdown('<p class="agent-text">No zone data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)
    elif "Agent 4" in page_name:
        data = state.all_subarea_rows
        if data:
            cols = [c for c in ["zone_name", "subarea_name", "city", "country", "business_volume", "status"] if c in data[0]]
            st.dataframe(pd.DataFrame(data)[cols], width="stretch")
        else: st.markdown('<p class="agent-text">No sub-area data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)
    elif "Agent 5" in page_name:
        st.markdown('<p class="agent-text">Supabase insertion status.</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="agent-text"><b>Subareas Insert:</b> {st.session_state.agent_status.get(4.5, "Pending")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="agent-text"><b>Leads Insert:</b> {st.session_state.agent_status.get(5.5, "Pending")}</p>', unsafe_allow_html=True)
    elif "Agent 6" in page_name:
        data = state.scraped_companies
        if data:
            cols = [c for c in ["company_name", "category", "priority", "subarea_name", "zone_name", "city_name"] if c in data[0]]
            st.dataframe(pd.DataFrame(data)[cols], width="stretch")
        else: st.markdown('<p class="agent-text">No scraped company data yet. Execute the pipeline from the Dashboard.</p>', unsafe_allow_html=True)

# ── Main App Assembly ───────────────────────────────────────

render_header()
render_sidebar()

if st.session_state.page == "Dashboard":
    render_execute_card()
    sel_c, sel_ci, sel_z, sel_sa = render_data_explorer()
    render_bottom_section(sel_c, sel_ci, sel_z, sel_sa)
else:
    render_agent_page(st.session_state.page)

if st.session_state.pipeline_running:
    time.sleep(1)
    st.rerun()