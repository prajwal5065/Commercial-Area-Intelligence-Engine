import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def main():
    print("Creating session...")
    resp = requests.post(f"{BASE_URL}/sessions")
    resp.raise_for_status()
    session_id = resp.json()["session_id"]
    print(f"Session ID: {session_id}")

    print("Running Agent 2 for India...")
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/agents/2/run", json={
        "selected_countries": ["India"],
        "provider": "groq"
    })
    resp.raise_for_status()

    while True:
        status_resp = requests.get(f"{BASE_URL}/sessions/{session_id}/status")
        status = status_resp.json()["agent_status"]["2"]
        print(f"Status: {status}")
        if status in ("Done", "Error"):
            break
        time.sleep(1)
        
    print("Fetching cities data...")
    data_resp = requests.get(f"{BASE_URL}/sessions/{session_id}/data/cities")
    cities = data_resp.json()
    print(f"Cities found: {len(cities)}")
    if cities:
        print(f"First city: {cities[0]}")

if __name__ == "__main__":
    main()
