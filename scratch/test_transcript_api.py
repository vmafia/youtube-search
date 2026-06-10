import os
import sys
from youtube_transcript_api import YouTubeTranscriptApi

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cookies_path = os.path.join(base_dir, "cookies.txt")
video_id = "ZqXDmBl6WMU"

print(f"Using cookies path: {cookies_path}")
try:
    if os.path.exists(cookies_path):
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
    else:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
    print("SUCCESS!")
    print(f"Transcript lines: {len(transcript)}")
    print("First 3 lines:")
    for line in transcript[:3]:
        print(line)
except Exception as e:
    import traceback
    print("FAILED!")
    traceback.print_exc()
