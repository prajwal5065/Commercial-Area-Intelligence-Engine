import time
import logging
from datetime import datetime
from langgraph.graph import StateGraph, END
from execution_state import ExecutionState, node_load_subareas, node_run_swarm

# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ==========================================
# GRAPH CONSTRUCTION
# ==========================================

def build_graph() -> StateGraph:
    graph = StateGraph(ExecutionState)
    
    graph.add_node("load_subareas", node_load_subareas)
    graph.add_node("run_swarm", node_run_swarm)
    
    graph.set_entry_point("load_subareas")
    graph.add_edge("load_subareas", "run_swarm")
    graph.add_edge("run_swarm", END)
    
    return graph.compile()


# ==========================================
# MAIN
# ==========================================

def main():
    print("=" * 60)
    print("SUB-AGENT 5 - EXECUTION ENGINE")
    print("=" * 60)

    start_time = time.time()
    
    initial_state: ExecutionState = {
        "subareas": [],
        "total_companies": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0
    }

    agent = build_graph()
    
    try:
        final_state = agent.invoke(initial_state)
    except Exception as e:
        log.critical(f"Execution Engine crashed: {e}")
        final_state = initial_state

    end_time = time.time()
    duration = round(end_time - start_time, 2)
    
    total = final_state.get("completed", 0) + final_state.get("failed", 0) + final_state.get("skipped", 0)

    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Total Subareas   : {total}")
    print(f"Completed        : {final_state.get('completed', 0)}")
    print(f"Skipped          : {final_state.get('skipped', 0)}")
    print(f"Failed           : {final_state.get('failed', 0)}")
    print(f"Companies Scraped: {final_state.get('total_companies', 0)}")
    print(f"Execution Time   : {duration} seconds")
    print("=" * 60)


if __name__ == "__main__":
    main()
