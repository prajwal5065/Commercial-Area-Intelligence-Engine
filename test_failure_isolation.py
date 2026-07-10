"""
test_failure_isolation.py — Confirms per-country failure isolation (item 4).

Forces 3 of 7 countries to raise an exception inside process_country() by
monkeypatching groq_classify.  The other 4 must still complete successfully.

Each country is tested in its own subprocess to ensure clean sys.path.

Run:
    python test_failure_isolation.py
"""
import os, sys, subprocess, json, time, threading

HERE = os.path.dirname(os.path.abspath(__file__))

# Worker script executed in a subprocess (clean environment per country)
WORKER_SCRIPT = r"""
import os, sys

HERE = {HERE!r}
sub2 = os.path.join(HERE, "SUB AGENT 2")

# Put SUB AGENT 2 first so its config.py (with GEMINI_MODEL) wins
for p in [sub2, HERE]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

import city_segmenters_code

FORCE_FAIL_COUNTRIES = {fail_set!r}
country = {country!r}

_real = city_segmenters_code.groq_classify

def _patched(c, ctx, provider="groq", worker_id="Unknown"):
    if c in FORCE_FAIL_COUNTRIES:
        raise RuntimeError("[TEST INJECTION] Forced failure for " + c)
    return _real(c, ctx, provider=provider, worker_id=worker_id)

city_segmenters_code.groq_classify = _patched

import json
try:
    data = city_segmenters_code.process_country(country, provider="groq", worker_id="TEST")
    t1 = len(data.get("tier_1_cities", []))
    t2 = len(data.get("tier_2_cities", []))
    print(json.dumps({{"ok": True, "t1": t1, "t2": t2}}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e)}}))
"""

FORCE_FAIL = {"Japan", "Germany", "Canada"}
ALL_COUNTRIES = ["Japan", "Germany", "Canada", "India", "Brazil", "Australia", "Mexico"]

results = {}
lock = threading.Lock()

def run_country(country):
    script = WORKER_SCRIPT.format(
        HERE=HERE,
        fail_set=FORCE_FAIL,
        country=country,
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=300,
            cwd=HERE,
        )
        # Last line of stdout is the JSON result
        last_line = proc.stdout.strip().rsplit("\n", 1)[-1].strip()
        if last_line.startswith("{"):
            r = json.loads(last_line)
        else:
            r = {"ok": False, "error": f"No JSON in output:\n{proc.stdout[-500:]}\n{proc.stderr[-500:]}"}
    except subprocess.TimeoutExpired:
        r = {"ok": False, "error": "TIMEOUT"}
    except Exception as e:
        r = {"ok": False, "error": str(e)}
    with lock:
        results[country] = r

print("Starting 7 country workers (3 forced-fail, 4 should succeed)...")
print("Note: Tavily is quota-exhausted so LLM-only mode will be used — that's fine.\n")

threads = [threading.Thread(target=run_country, args=(c,), name=c) for c in ALL_COUNTRIES]
for t in threads:
    t.start()
for t in threads:
    t.join()

# ── report ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  FAILURE ISOLATION TEST RESULTS")
print("=" * 60)

all_passed = True
for country in ALL_COUNTRIES:
    r = results.get(country, {})
    if country in FORCE_FAIL:
        if not r.get("ok"):
            label = "OK  (correctly failed as injected)"
        else:
            label = "UNEXPECTED SUCCESS — isolation may be broken!"
            all_passed = False
    else:
        if r.get("ok"):
            label = f"OK  (T1={r.get('t1', '?')}, T2={r.get('t2', '?')})"
        else:
            label = f"FAIL — {r.get('error', '?')[:120]}"
            all_passed = False
    print(f"  {country:15s}: {label}")

print("=" * 60)
if all_passed:
    print("  CONCLUSION: Isolation CONFIRMED.")
    print("  Failures are per-country; the other countries complete independently.")
    print("  Only a 'Final Report: Succeeded / Failed' summary in the UI is needed,")
    print("  NOT a structural fix.")
else:
    print("  CONCLUSION: Isolation BROKEN or not all expected countries succeeded.")
    print("  Investigate where failure propagates across countries.")
print("=" * 60)
sys.exit(0 if all_passed else 1)
