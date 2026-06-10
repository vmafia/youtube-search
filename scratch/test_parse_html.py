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
res = requests.get(url, headers=headers)

# Search for ytInitialPlayerResponse
match = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?});", res.text)
if match:
    player_response = json.loads(match.group(1))
    print("Found ytInitialPlayerResponse!")
    captions = player_response.get("captions", {})
    print("Captions Keys:", captions.keys())
    if "playerCaptionsTracklistRenderer" in captions:
        tracks = captions["playerCaptionsTracklistRenderer"].get("captionTracks", [])
        print("Caption Tracks found:")
        for t in tracks:
            print(f"- LanguageCode: {t.get('languageCode')}, Kind: {t.get('kind', 'standard')}, URL: {t.get('baseUrl')[:100]}...")
    else:
        print("playerCaptionsTracklistRenderer NOT found in captions.")
else:
    # Try finding inside var ytInitialPlayerResponse = {...} without semicolon
    match2 = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?})\s*</script>", res.text)
    if match2:
        player_response = json.loads(match2.group(1))
        print("Found ytInitialPlayerResponse (alternative)!")
        captions = player_response.get("captions", {})
        print("Captions Keys:", captions.keys())
    else:
        print("ytInitialPlayerResponse NOT found in HTML!")
        # Let's save a part of HTML to see if there is any indicator
        with open("scratch/page.html", "w", encoding="utf-8") as f:
            f.write(res.text[:100000])
