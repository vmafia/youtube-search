import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from youtube_transcript_api import YouTubeTranscriptApi

def test_api(video_id):
    logger.info(f"Testing YouTubeTranscriptApi for {video_id}...")
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
        cookies_path = os.path.join(base_dir, "cookies.txt")
    
    try:
        if os.path.exists(cookies_path):
            logger.info(f"Using cookies from {cookies_path}")
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
        else:
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
        logger.info(f"Successfully retrieved {len(fetched)} lines from YouTubeTranscriptApi")
        return True
    except Exception as e:
        logger.error(f"YouTubeTranscriptApi failed: {e}")
        return False

def test_yt_dlp(video_id):
    logger.info(f"Testing yt-dlp subtitles for {video_id}...")
    import subprocess
    import glob
    
    temp_dir = "D:\\youtube_search_temp"
    os.makedirs(temp_dir, exist_ok=True)
    output_tmpl = os.path.join(temp_dir, f"test_{video_id}")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
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
    
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
        cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
        
    cmd.append(video_url)
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        logger.info(f"yt-dlp stdout: {res.stdout}")
        logger.info(f"yt-dlp stderr: {res.stderr}")
        
        pattern = os.path.join(temp_dir, f"test_{video_id}.*vtt")
        matches = glob.glob(pattern)
        if matches:
            logger.info(f"Found subtitle files: {matches}")
            for m in matches:
                os.remove(m)
            return True
        else:
            logger.warning("No subtitle files downloaded by yt-dlp")
            return False
    except Exception as e:
        logger.error(f"yt-dlp subprocess run failed: {e}")
        return False

if __name__ == "__main__":
    vid = "fKNhhDb-8xs"
    if len(sys.argv) > 1:
        vid = sys.argv[1]
    
    api_ok = test_api(vid)
    yt_ok = test_yt_dlp(vid)
    logger.info(f"Results for {vid}: API={api_ok}, yt-dlp={yt_ok}")
