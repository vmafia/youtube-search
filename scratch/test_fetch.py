import sys
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "JsQHC_2I4gw"
if len(sys.argv) > 1:
    video_id = sys.argv[1]

print(f"Fetching transcript for: {video_id}")
try:
    fetched = YouTubeTranscriptApi().fetch(video_id, languages=["th", "en"])
    transcript = [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
    print("Success!")
    # Avoid encoding crash when printing Thai characters by printing only count and ASCII representation
    print(f"Retrieved {len(transcript)} snippets.")
    if transcript:
        first = transcript[0]
        print(f"First snippet: start={first['start']}, duration={first['duration']}, text_len={len(first['text'])}")
except Exception as e:
    print(f"Failed: {type(e).__name__}: {e}")
