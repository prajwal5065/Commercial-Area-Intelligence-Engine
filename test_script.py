import requests, time

print("Creating session...")
res = requests.post("http://localhost:8000/sessions")
sid = res.json()["session_id"]
print(f"Session: {sid}")

print("Running Agent 1...")
requests.post(f"http://localhost:8000/sessions/{sid}/agents/1/run", json={"top_n": 1})

while True:
    status = requests.get(f"http://localhost:8000/sessions/{sid}/status").json()
    if status["agent_status"].get("1") == "Done":
        break
    time.sleep(2)
print("Agent 1 Done")

print("Running Agent 2...")
requests.post(f"http://localhost:8000/sessions/{sid}/agents/2/run", json={"selected_countries": [], "provider": "groq"})

while True:
    status = requests.get(f"http://localhost:8000/sessions/{sid}/status").json()
    if status["agent_status"].get("2") in ["Done", "Error", "Failed"]:
        print(f"Agent 2 Status: {status['agent_status']['2']}")
        break
    time.sleep(2)

print("Fetching cities...")
cities = requests.get(f"http://localhost:8000/sessions/{sid}/data/cities").json()
print(f"Cities ({len(cities)}): {cities[:5]}")
