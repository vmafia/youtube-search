import sys
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "JsQHC_2I4gw"
if len(sys.argv) > 1:
    video_id = sys.argv[1]

print(f"Fetching transcript for: {video_id}")
try:
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
    print("Success!")
    print(transcript[:5])
except Exception as e:
    print(f"Failed: {type(e).__name__}: {e}")
