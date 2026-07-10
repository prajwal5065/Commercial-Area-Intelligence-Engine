"""
diagnostic_test.py — Step 0 diagnostic
Run Agent 2 (city_segmenters_code.process_country) with exactly
1 country and 1 worker.  Confirms whether the failure is a concurrency
problem or something more fundamental.

Usage:
    python diagnostic_test.py
"""
import os, sys, time, logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── path bootstrap ─────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sub2 = os.path.join(HERE, "SUB AGENT 2")
for p in [sub2, HERE]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

import city_segmenters_code

COUNTRY = "Japan"   # small-but-real country so the test completes quickly

print("=" * 60)
print(f"  DIAGNOSTIC: Agent 2 — 1 country, 1 worker")
print(f"  Country : {COUNTRY}")
print(f"  Provider: groq")
print("=" * 60)

t0 = time.time()
try:
    result = city_segmenters_code.process_country(
        COUNTRY, provider="groq", worker_id="DIAG-01"
    )
    elapsed = time.time() - t0
    t1 = len(result.get("tier_1_cities", []))
    t2 = len(result.get("tier_2_cities", []))
    t3_groups = result.get("tier_3_cities", [])
    t3 = sum(len(g.get("cities", [g])) if isinstance(g, dict) else 0 for g in t3_groups)
    print("\n" + "=" * 60)
    print(f"  RESULT: SUCCESS")
    print(f"  Elapsed : {elapsed:.1f}s")
    print(f"  Tier 1  : {t1} cities")
    print(f"  Tier 2  : {t2} cities")
    print(f"  Tier 3  : {t3} sample cities")
    print("=" * 60)
    sys.exit(0)
except Exception as e:
    elapsed = time.time() - t0
    import traceback
    print("\n" + "=" * 60)
    print(f"  RESULT: FAILED")
    print(f"  Elapsed : {elapsed:.1f}s")
    print(f"  Error   : {type(e).__name__}: {e}")
    print("  Traceback:")
    traceback.print_exc()
    print("=" * 60)
    print("\nDIAGNOSTIC CONCLUSION: Problem is NOT concurrency/rate-limiting.")
    print("Do NOT apply the semaphore/stagger/backoff fixes until the root cause is resolved.")
    sys.exit(1)
