import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

print("Key:", api_key[:15] + "..." if api_key else "NOT FOUND")

payload = {
    "api_key": api_key,
    "query": "India",
    "search_depth": "basic",
    "max_results": 3
}

response = requests.post(
    "https://api.tavily.com/search",
    json=payload
)

print("Status Code:", response.status_code)
print(response.text)