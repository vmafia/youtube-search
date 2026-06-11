import os
import requests
import json
import re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cookies_path = os.path.join(base_dir, "cookies.txt")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

cookies = {}
if os.path.exists(cookies_path):
    with open(cookies_path, "r") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]

url = "https://www.youtube.com/watch?v=WAN704dCy-g"
print("Fetching watch page with cookies...")
res = requests.get(url, headers=headers, cookies=cookies)

match = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?});", res.text)
if not match:
    match = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?})\s*</script>", res.text)

if match:
    player_response = json.loads(match.group(1))
    captions = player_response.get("captions", {})
    if "playerCaptionsTracklistRenderer" in captions:
        tracks = captions["playerCaptionsTracklistRenderer"].get("captionTracks", [])
        if tracks:
            track_url = tracks[0]["baseUrl"]
            print("Found Caption Track URL:", track_url)
            print("Fetching timedtext transcript with cookies...")
            sub_res = requests.get(track_url, headers=headers, cookies=cookies)
            print("Timedtext Status Code:", sub_res.status_code)
            print("Response Length:", len(sub_res.text))
            print("Content Snippet:")
            print(sub_res.text[:1000])
        else:
            print("No caption tracks found.")
    else:
        print("playerCaptionsTracklistRenderer not found.")
else:
    print("ytInitialPlayerResponse not found.")
