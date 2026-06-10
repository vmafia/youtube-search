import requests
import json
import re
import xml.etree.ElementTree as ET

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

url = "https://www.youtube.com/watch?v=WAN704dCy-g"
print("Fetching watch page...")
res = requests.get(url, headers=headers)

match = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?});", res.text)
if not match:
    # Alternative match
    match = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?})\s*</script>", res.text)

if match:
    player_response = json.loads(match.group(1))
    captions = player_response.get("captions", {})
    if "playerCaptionsTracklistRenderer" in captions:
        tracks = captions["playerCaptionsTracklistRenderer"].get("captionTracks", [])
        if tracks:
            # Let's pick the first track (Thai/English)
            track_url = tracks[0]["baseUrl"]
            print("Found Caption Track URL:", track_url)
            # Add format=vtt or format=json3 parameter if desired, or just download XML
            # Let's request the timedtext URL
            print("Fetching timedtext transcript...")
            sub_res = requests.get(track_url, headers=headers)
            print("Timedtext Status Code:", sub_res.status_code)
            print("Content Snippet:")
            print(sub_res.text[:300])
        else:
            print("No caption tracks in list.")
    else:
        print("playerCaptionsTracklistRenderer not in captions.")
else:
    print("ytInitialPlayerResponse not found.")
