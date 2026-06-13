import os
import sys
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "WAN704dCy-g"
print("Testing with YouTubeTranscriptApi().fetch...")
try:
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=["th", "en"])
    print("SUCCESS!")
    print(f"Transcript lines: {len(fetched)}")
    print("First 3 lines:")
    for line in list(fetched)[:3]:
        print(f"Text: {line.text} | Start: {line.start} | Duration: {line.duration}")
except Exception as e:
    import traceback
    print("FAILED!")
    traceback.print_exc()
