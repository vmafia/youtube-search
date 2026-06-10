import os
import requests

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cookies_path = os.path.join(base_dir, "cookies.txt")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

cookies = {}
if os.path.exists(cookies_path):
    print("Loading cookies...")
    with open(cookies_path, "r") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]

url = "https://www.youtube.com/watch?v=ZqXDmBl6WMU"
res = requests.get(url, headers=headers, cookies=cookies)
print("Status Code:", res.status_code)
print("Content Length:", len(res.text))
print("First 500 chars of HTML:")
print(res.text[:500])

if "consent" in res.url or "google.com/sorry" in res.url:
    print("Redirected to:", res.url)
