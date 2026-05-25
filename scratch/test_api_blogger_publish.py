import requests
import json
import time

url = "http://localhost:8000/campaign/publish/blogger"
payload = {
    "total_articles": 3,
    "max_workers": 3
}
headers = {
    "Content-Type": "application/json"
}

print("[SEND] Sending request to API to generate 3 articles and publish to Blogger...")
start_time = time.time()
try:
    response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=600)
    duration = time.time() - start_time
    print(f"[TIME] Request completed in {duration:.2f} seconds.")
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"[ERROR] Failed to reach API or request timed out: {e}")
