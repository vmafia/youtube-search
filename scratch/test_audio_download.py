import os
import sys
import subprocess

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cookies_path = os.path.join(base_dir, "cookies.txt")
video_id = "2nNE-wNVV-k"
audio_path_tmpl = os.path.join(base_dir, "scratch", "temp_subs", f"{video_id}.%(ext)s")
video_url = f"https://www.youtube.com/watch?v={video_id}"

cmd = [
    sys.executable, "-m", "yt_dlp",
    "-f", "ba[ext=m4a]/ba",
    "-x", "--audio-format", "m4a",
    "--js-runtimes", "node",
    "--extractor-args", "youtube:player_client=web",
    "-o", audio_path_tmpl
]

if os.path.exists(cookies_path):
    cmd.extend(["--cookies", cookies_path])

cmd.append(video_url)

print("Running command:", " ".join(cmd))
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:")
print(res.stdout)
print("STDERR:")
print(res.stderr)
