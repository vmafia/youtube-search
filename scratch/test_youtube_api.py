from youtube_transcript_api import YouTubeTranscriptApi
import sys

video_id = "2nNE-wNVV-k"
cookies_path = "cookies_new.txt"

try:
    print(f"Testing get_transcript with cookies from '{cookies_path}'...")
    fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
    print(f"Success! Fetched {len(fetched)} segments.")
    print("First 3 segments:", fetched[:3])
except Exception as e:
    print(f"get_transcript with cookies failed: {e}")
