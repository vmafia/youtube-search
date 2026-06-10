import os
import sys
import subprocess

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
temp_dir = os.path.join(base_dir, "scratch", "temp_subs_test")
os.makedirs(temp_dir, exist_ok=True)

video_id = "WAN704dCy-g"  # One of the videos
output_tmpl = os.path.join(temp_dir, f"{video_id}")
video_url = f"https://www.youtube.com/watch?v={video_id}"

cmd = [
    sys.executable, "-m", "yt_dlp",
    "--write-auto-subs",
    "--write-subs",
    "--skip-download",
    "--sub-langs", "th",
    "--sub-format", "vtt",
    "--js-runtimes", "node",
    "-o", output_tmpl
]

cookies_path = os.path.join(base_dir, "cookies.txt")
if os.path.exists(cookies_path):
    cmd.extend(["--cookies", cookies_path])
    print(f"Using cookies path: {cookies_path}")
else:
    print("No cookies.txt found!")

cmd.append(video_url)

print("Running command:", " ".join(cmd))
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:")
print(res.stdout)
print("STDERR:")
print(res.stderr)
