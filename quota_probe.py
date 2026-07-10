"""
quota_probe.py — Steps 1–4 of the quota isolation investigation.

Tests in order:
  A) Probe the Gemini REST API for the model list and quota headers
  B) Single-worker, single-country — gemini-2.0-flash  (step 2a)
  C) Single-worker, single-country — gemini-1.5-flash  (step 2b)
  D) Single-worker, single-country — groq              (step 3)
  E) Single direct raw call to gemini-3-pro-preview to capture raw error body

All tests use the same COUNTRY = "Japan" (small, fast to process).
No code changes — reads only.  Shows the raw HTTP status + body on failure.

Usage:
    python quota_probe.py
"""

import os, sys, time, json, requests
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sub2 = os.path.join(HERE, "SUB AGENT 2")
for p in [sub2, HERE]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
COUNTRY        = "Japan"

SEP = "=" * 65

def hdr(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ══════════════════════════════════════════════════════════════════
#  STEP 1 — Probe Gemini model info + quota signals from the API
# ══════════════════════════════════════════════════════════════════
hdr("STEP 1 — Gemini model list probe (quota signals via REST)")

models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
try:
    r = requests.get(models_url, timeout=15)
    print(f"  HTTP status : {r.status_code}")
    print(f"  Rate-limit headers:")
    rl_headers = {k: v for k, v in r.headers.items()
                  if any(x in k.lower() for x in ["rate", "quota", "limit", "retry", "remaining", "reset", "x-ratelimit"])}
    if rl_headers:
        for k, v in rl_headers.items():
            print(f"    {k}: {v}")
    else:
        print("    (none exposed in response headers)")

    if r.status_code == 200:
        models = r.json().get("models", [])
        target_names = ["gemini-3-pro-preview", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
        print(f"\n  Models in API response matching targets:")
        found = {m["name"].split("/")[-1]: m for m in models}
        for name in target_names:
            m = found.get(name)
            if m:
                print(f"    {name}: displayName={m.get('displayName','?')}, "
                      f"inputTokenLimit={m.get('inputTokenLimit','?')}, "
                      f"outputTokenLimit={m.get('outputTokenLimit','?')}")
            else:
                print(f"    {name}: NOT FOUND in API — key may lack access to this model")
    else:
        print(f"  Error body: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 1b — Raw call to gemini-3-pro-preview to capture exact error
# ══════════════════════════════════════════════════════════════════
hdr("STEP 1b — Raw call: gemini-3-pro-preview (capture error body)")

preview_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent?key={GEMINI_API_KEY}"
preview_payload = {
    "contents": [{"role": "user", "parts": [{"text": "Say: hello"}]}],
    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 20},
}
t0 = time.time()
try:
    r = requests.post(preview_url, json=preview_payload, timeout=30)
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    print(f"  Headers of interest:")
    for k, v in r.headers.items():
        if any(x in k.lower() for x in ["rate", "quota", "limit", "retry", "remaining", "reset"]):
            print(f"    {k}: {v}")
    try:
        body = r.json()
        print(f"  Response body:\n{json.dumps(body, indent=2)[:1200]}")
    except Exception:
        print(f"  Raw body: {r.text[:800]}")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 2a — Single worker, gemini-2.0-flash
# ══════════════════════════════════════════════════════════════════
hdr("STEP 2a — Single worker, gemini-2.0-flash")

flash_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
flash_payload = {
    "contents": [{"role": "user", "parts": [{"text": f"List the 3 largest cities in {COUNTRY} in JSON."}]}],
    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
}
t0 = time.time()
try:
    r = requests.post(flash_url, json=flash_payload, timeout=30)
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    if r.status_code == 200:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(f"  Result      : SUCCESS")
        print(f"  Response    : {text[:300]}")
    else:
        try:
            body = r.json()
            print(f"  FAILED — body:\n{json.dumps(body, indent=2)[:800]}")
        except Exception:
            print(f"  FAILED — raw: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 2b — Single worker, gemini-1.5-flash
# ══════════════════════════════════════════════════════════════════
hdr("STEP 2b — Single worker, gemini-1.5-flash")

flash15_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
t0 = time.time()
try:
    r = requests.post(flash15_url, json=flash_payload, timeout=30)
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    if r.status_code == 200:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(f"  Result      : SUCCESS")
        print(f"  Response    : {text[:300]}")
    else:
        try:
            body = r.json()
            print(f"  FAILED — body:\n{json.dumps(body, indent=2)[:800]}")
        except Exception:
            print(f"  FAILED — raw: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 2c — Single worker, gemini-1.5-pro
# ══════════════════════════════════════════════════════════════════
hdr("STEP 2c — Single worker, gemini-1.5-pro")

pro15_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
t0 = time.time()
try:
    r = requests.post(pro15_url, json=flash_payload, timeout=30)
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    if r.status_code == 200:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(f"  Result      : SUCCESS")
        print(f"  Response    : {text[:300]}")
    else:
        try:
            body = r.json()
            print(f"  FAILED — body:\n{json.dumps(body, indent=2)[:800]}")
        except Exception:
            print(f"  FAILED — raw: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 3 — Single worker, Groq (llama-3.3-70b-versatile)
# ══════════════════════════════════════════════════════════════════
hdr("STEP 3 — Single worker, Groq (llama-3.3-70b-versatile)")

groq_url = "https://api.groq.com/openai/v1/chat/completions"
groq_payload = {
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.1,
    "max_tokens": 200,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"List the 3 largest cities in {COUNTRY} in JSON."},
    ],
}
t0 = time.time()
try:
    r = requests.post(
        groq_url,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=groq_payload, timeout=30,
    )
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    if r.status_code == 200:
        text = r.json()["choices"][0]["message"]["content"]
        print(f"  Result      : SUCCESS")
        print(f"  Response    : {text[:300]}")
    else:
        try:
            body = r.json()
            print(f"  FAILED — body:\n{json.dumps(body, indent=2)[:800]}")
        except Exception:
            print(f"  FAILED — raw: {r.text[:500]}")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  STEP 4 — Tavily quota check (confirm 432 = plan limit, not code)
# ══════════════════════════════════════════════════════════════════
hdr("STEP 4 — Tavily plan-limit probe")

tavily_url = "https://api.tavily.com/search"
tavily_payload = {
    "api_key": TAVILY_API_KEY,
    "query": "Japan city classification",
    "search_depth": "basic",
    "max_results": 1,
}
t0 = time.time()
try:
    r = requests.post(tavily_url, json=tavily_payload, timeout=15)
    elapsed = time.time() - t0
    print(f"  HTTP status : {r.status_code}  ({elapsed:.1f}s)")
    try:
        body = r.json()
        print(f"  Body: {json.dumps(body, indent=2)[:500]}")
    except Exception:
        print(f"  Raw: {r.text[:300]}")
    if r.status_code == 432:
        print("\n  CONFIRMED: Tavily 432 = plan/billing quota exhausted.")
        print("  Action needed: upgrade Tavily plan or reduce usage.")
        print("  Code is NOT at fault — LLM-only fallback already handles this.")
    elif r.status_code == 200:
        print("\n  UNEXPECTED: Tavily succeeded — quota may have reset.")
except Exception as e:
    print(f"  Exception: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════
hdr("INVESTIGATION COMPLETE — review results above")
print("""
  Key questions this run answers:
    Q1: Is gemini-3-pro-preview accessible at all with this API key?
    Q2: Does gemini-2.0-flash / 1.5-flash / 1.5-pro work where preview fails?
    Q3: Does Groq handle an isolated single request cleanly?
    Q4: Is Tavily 432 a plan/billing issue (confirmed by status code)?
""")
