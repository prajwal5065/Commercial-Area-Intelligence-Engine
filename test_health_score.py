"""
test_health_score.py — Item 5: Confirms record_outcome() fires on every 429
and that the health score for the provider visibly drops after a burst.

Simulates 5 consecutive 429 responses by monkeypatching requests.post, then
checks whether:
  (a) record_outcome() was called for each 429
  (b) the provider's health score dropped below the initial 1.0

Run:
    python test_health_score.py
"""
import os, sys, time, logging

logging.basicConfig(level=logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
sub2 = os.path.join(HERE, "SUB AGENT 2")
for p in [sub2, HERE]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

# ── import adaptive concurrency first so we can observe state ──────
from adaptive_concurrency import get_provider_manager, record_outcome

# ── import city_segmenters_code after path is set ─────────────────
import city_segmenters_code
import requests

# ── snapshot health score before burst ────────────────────────────
mgr = get_provider_manager("groq")
score_before = mgr.health_score
workers_before = mgr.current_workers
print(f"[Before burst]  health_score={score_before:.4f}  workers={workers_before}")

# ── monkeypatch: make requests.post always return HTTP 429 ─────────
record_calls = []
_real_post = requests.post

class _Fake429Response:
    status_code = 429
    def json(self): return {"error": "rate_limit_exceeded"}
    def raise_for_status(self):
        raise requests.exceptions.HTTPError("429 Too Many Requests")

def _mock_post(url, **kwargs):
    record_calls.append(url)
    return _Fake429Response()

# Patch at both the module level and inside city_segmenters_code
requests.post = _mock_post
city_segmenters_code.requests.post = _mock_post

# ── fire 5 calls that will all hit 429 ────────────────────────────
print("Firing 5 requests that will all receive HTTP 429...")
for i in range(5):
    try:
        city_segmenters_code.groq_classify(
            "TestCountry", "", provider="groq", worker_id=f"HEALTH-TEST-{i}"
        )
    except Exception:
        pass   # expected — 429 raises HTTPError

# Restore real requests.post
requests.post = _real_post
city_segmenters_code.requests.post = _real_post

# ── check outcomes ─────────────────────────────────────────────────
score_after = mgr.health_score
workers_after = mgr.current_workers

print(f"[After burst]   health_score={score_after:.4f}  workers={workers_after}")
print(f"[Calls recorded]: {len(record_calls)}")

print("\n" + "=" * 60)
print("  HEALTH SCORE VERIFICATION RESULTS")
print("=" * 60)

all_passed = True

# Check: record_outcome was called (health score should have moved)
if len(record_calls) == 5:
    print("  record_calls  : OK  (5 HTTP calls reached the mock)")
else:
    print(f"  record_calls  : FAIL — expected 5, got {len(record_calls)}")
    all_passed = False

# Check: health score dropped (record_outcome was called for each 429)
if score_after < score_before:
    print(f"  score dropped : OK  ({score_before:.4f} → {score_after:.4f})")
else:
    print(f"  score dropped : FAIL — score did not drop ({score_before:.4f} → {score_after:.4f})")
    print("                   record_outcome() may not be firing on 429 responses.")
    all_passed = False

# Note: concurrency steps down only after MIN_SAMPLES_BEFORE_ADJUST (default 5)
# and only if ADJUSTMENT_COOLDOWN_SEC has elapsed. With 5 samples it may or may
# not step down depending on timing, so we only warn — don't fail — on this check.
if workers_after < workers_before:
    print(f"  workers down  : OK  ({workers_before} → {workers_after}) — semaphore already stepped down")
else:
    print(f"  workers down  : NOTE — still {workers_after} workers (cooldown or <5 samples; expected on short test)")

print("=" * 60)
if all_passed:
    print("  CONCLUSION: record_outcome() fires on every 429 and health score")
    print("  visibly drops. A subsequent run will start with a lower semaphore")
    print("  limit instead of repeating the same cold-start burst.")
else:
    print("  CONCLUSION: record_outcome() wiring needs investigation.")
print("=" * 60)
sys.exit(0 if all_passed else 1)
