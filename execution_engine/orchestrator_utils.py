"""
orchestrator_utils.py — Master Agent Orchestrator Protocol Library
====================================================================
Provides shared utilities for the unified concurrent pipeline:
  - Batch calculation with K = ceil(N / C_max) and remainder distribution
  - Planning/Dispatch block printing for transparency
  - Fault-tolerant worker dispatch with retry + drop logic
  - PipelineState to accumulate results across all phases
"""

import math
import json
import traceback as _traceback
from typing import List, Dict, Any, Callable, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import sys

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



# ═══════════════════════════════════════════════════════════════════
#  Batch Calculation
# ═══════════════════════════════════════════════════════════════════

def calculate_batches(items: List[Any], c_max: int = 3, agent_name: str = "Agent") -> List[Dict]:
    """
    Calculate batch division for parallel dispatch.
    
    Formula: K = ceil(N / C_max)
    - N: total number of items
    - C_max: maximum items per batch/instance
    - K: number of parallel batches (instances) needed
    - Remainder distribution: last batch gets overflow
    
    Args:
        items: List of items to batch
        c_max: Max items per batch
        agent_name: Prefix for instance IDs (e.g., 'Agent2')
    
    Returns:
        List[Dict] with keys: instance_id, items, batch_index, total_batches
    """
    if not items or c_max <= 0:
        return []
    
    N = len(items)
    K = math.ceil(N / c_max)
    
    batches = []
    for k in range(K):
        start_idx = k * c_max
        end_idx = start_idx + c_max
        batch_items = items[start_idx:end_idx]
        
        instance_id = f"{agent_name}-Clone-{k+1:02d}"
        batches.append({
            "instance_id": instance_id,
            "items": batch_items,
            "batch_index": k,
            "total_batches": K,
        })
    
    return batches


# ═══════════════════════════════════════════════════════════════════
#  Planning Block Printing
# ═══════════════════════════════════════════════════════════════════

def print_planning_block(phase_num: int, phase_name: str, total_items: int,
                        c_max: int, K: int, item_label: str = "items") -> None:
    """
    Print a standardized planning block for a phase.
    
    Shows: Phase number, name, total items, batch capacity, instance count.
    """
    print("\n" + "=" * 60)
    print(f"  PHASE {phase_num} PLANNING: {phase_name}")
    print("=" * 60)
    print(f"  Total {item_label}: N = {total_items}")
    print(f"  Capacity per instance: C_max = {c_max} {item_label}")
    print(f"  Required instances: K = ceil({total_items} / {c_max}) = {K}")
    print("=" * 60 + "\n")


# ===================================================================
#  Dispatch Block Printing
# ===================================================================

def print_dispatch_block(agent_name: str, instance_id: str, input_data: List[Any],
                        expected_output_desc: str) -> None:
    """
    Print a standardized dispatch block for an instance.
    
    Shows: Agent name, instance ID, input items, expected output format.
    """
    input_str = ", ".join(str(item) for item in input_data[:3])
    if len(input_data) > 3:
        input_str += f", ... (+{len(input_data) - 3} more)"
    
    print(f"  +- [{instance_id}]")
    print(f"  | Agent: {agent_name}")
    print(f"  | Input: [{input_str}]")
    print(f"  | Expected Output: {expected_output_desc}")
    print(f"  +-")


# ═══════════════════════════════════════════════════════════════════
#  Fault-Tolerant Worker Dispatch
# ═══════════════════════════════════════════════════════════════════

def fault_tolerant_dispatch(worker_fn: Callable, batches: List[Dict],
                            agent_name: str = "Agent", max_workers: int = 5,
                            max_retries: int = 1, on_active_change: Optional[Callable[[int], None]] = None) -> Tuple[List, List]:
    """
    Execute worker function across batches with fault tolerance.
    
    Protocol:
    1. Dispatch batch to worker_fn(batch_items, instance_id)
    2. If error: retry up to max_retries times
    3. If still fails: log as dropped slice, continue
    4. Collect successful results and failure log
    
    Args:
        worker_fn: Async function(batch_items, instance_id) -> result
        batches: List of batch dicts with 'items' and 'instance_id'
        agent_name: Agent name for logging
        max_workers: Max concurrent threads
        max_retries: Max retries per batch before dropping
    
    Returns:
        Tuple[List[results], List[failure_dicts]]
    """
    results = []
    failures = []
    
    def execute_batch_with_retry(batch: Dict) -> Tuple[Any, Dict]:
        instance_id = batch["instance_id"]
        items = batch["items"]
        
        for attempt in range(max_retries + 1):
            try:
                if on_active_change:
                    on_active_change(1)
                try:
                    result = worker_fn(items, instance_id)
                finally:
                    if on_active_change:
                        on_active_change(-1)
                return result, None  # Success
            except Exception as e:
                if attempt < max_retries:
                    print(f"  [{instance_id}] Retry {attempt + 1}/{max_retries} after error: {e}")
                else:
                    # Final failure — log full traceback and drop
                    tb = _traceback.format_exc()
                    failure = {
                        "phase": agent_name,
                        "instance_id": instance_id,
                        "error": str(e),
                        "traceback": tb,
                        "items_count": len(items),
                    }
                    print(f"  [{instance_id}] ✗ DROPPED — Max retries exceeded.")
                    print(f"  [{instance_id}] Error: {e}")
                    print(f"  [{instance_id}] Traceback:\n{tb}")
                    return None, failure
        
        return None, None
    
    # Execute batches in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(execute_batch_with_retry, batch): batch
            for batch in batches
        }
        
        for future in as_completed(futures):
            result, failure = future.result()
            if failure:
                failures.append(failure)
            elif result is not None:
                results.append(result)
    
    return results, failures


# ═══════════════════════════════════════════════════════════════════
#  Pipeline State — Accumulator Across All Phases
# ═══════════════════════════════════════════════════════════════════

class PipelineState:
    """
    Stateful accumulator for entire pipeline execution.
    
    Accumulates:
    - Phase 1: GDP-ranked countries
    - Phase 2: Master City Registry + flattened all_cities
    - Phase 3: Master Zone Registry + flattened zones
    - Phase 4: Master Subarea Registry + flattened all_subarea_rows
    - Phase 5: Scraped companies (leads)
    - Failures: Dropped slices with error details
    """
    
    def __init__(self):
        # Phase 1 outputs
        self.gdp_ranked_countries = []  # [{"country_name": "...", "gdp_rank": N}]
        
        # Phase 2 outputs
        self.master_city_registry = {}  # {country: {tier_1_cities, tier_2_cities, tier_3_cities}}
        self.all_cities = []  # [{"city": "...", "country": "...", "tier": N}]
        
        # Phase 3 outputs
        self.master_zone_registry = {}  # {(city, country): [zone_names]}
        
        # Phase 4 outputs
        self.master_subarea_registry = {}  # {(zone, city, country): [subarea_objs]}
        self.all_subarea_rows = []  # [{"zone_name": "...", "subarea_name": "...", ...}]
        
        # Phase 5 outputs
        self.scraped_companies = []  # [{"company_name": "...", "category": "...", ...}]
        
        # Execution tracking
        self.failures = []  # [{"phase": "...", "instance_id": "...", "error": "..."}]
        self.start_time = datetime.now()
        self.on_failure_callback = None

    def log_failure(self, phase_name: str, failure_dict: Dict) -> None:
        """Log a dropped slice (failed batch execution)."""
        failure_dict["phase"] = phase_name
        self.failures.append(failure_dict)
        if self.on_failure_callback:
            try:
                self.on_failure_callback(phase_name, failure_dict)
            except Exception:
                pass
    
    def finalize(self) -> None:
        """Finalize pipeline state after all phases complete."""
        self.end_time = datetime.now()
        self.execution_duration = (self.end_time - self.start_time).total_seconds()
    
    def summary(self) -> None:
        """Print execution summary."""
        print("\n  PIPELINE EXECUTION SUMMARY")
        print("  ─" * 30)
        print(f"  Countries Processed     : {len(self.gdp_ranked_countries)}")
        print(f"  Cities Discovered       : {len(self.all_cities)}")
        print(f"  Zones Discovered        : {sum(len(z) for z in self.master_zone_registry.values())}")
        print(f"  Sub-Areas Discovered    : {len(self.all_subarea_rows)}")
        print(f"  Companies Scraped       : {len(self.scraped_companies)}")
        print(f"  Dropped Slices          : {len(self.failures)}")
        print(f"  Execution Time (seconds): {self.execution_duration:.2f}")
