import os
import sys
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from youtube_transcript_api import YouTubeTranscriptApi
import subprocess

video_id = "fKNhhDb-8xs"
cookies_path = os.path.join(base_dir, "cookies_new.txt")
if not os.path.exists(cookies_path):
    cookies_path = os.path.join(base_dir, "cookies.txt")

print(f"Testing YouTubeTranscriptApi with cookies from {cookies_path}...")
try:
    if os.path.exists(cookies_path):
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
    else:
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
    print("Success! Subtitles fetched using API. Length:", len(fetched))
except Exception as e:
    print("API Failed with exception:", type(e).__name__, "-", str(e))

print("\nTesting yt-dlp auto-subs download...")
output_tmpl = os.path.join(base_dir, "scratch", "temp_subs", f"{video_id}")
cmd = [
    sys.executable, "-m", "yt_dlp",
    "--write-auto-subs",
    "--write-subs",
    "--skip-download",
    "--sub-langs", "th",
    "--sub-format", "vtt",
    "--js-runtimes", "node",
    "--remote-components", "ejs:github",
    "-o", output_tmpl
]
if os.path.exists(cookies_path):
    cmd.extend(["--cookies", cookies_path])
cmd.append(f"https://www.youtube.com/watch?v={video_id}")

try:
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("yt-dlp exit code:", res.returncode)
    print("yt-dlp stdout:", res.stdout[:500])
    print("yt-dlp stderr:", res.stderr[:500])
except Exception as e:
    print("yt-dlp execution failed:", e)
