import os
import sys
import io
import time
import json
import argparse
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ Please install google-genai: pip install google-genai")
    sys.exit(1)

# Import DatabaseManager to save directly to Firebase/Local cache
sys.path.append(os.path.dirname(__file__))
from backend.utils.db import DatabaseManager
from backend.config import Config

API_URL = "http://localhost:5000"
CACHE_DIR = Config.CACHE_DIR
STATUS_FILE = os.path.join(CACHE_DIR, "transcription_status.json")

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[i]", "OK": "[OK]", "WARN": "[!]", "ERR": "[X]"}
    icon = icons.get(level, "   ")
    print(f"[{ts}] {icon} {msg}")

def update_status(status_data):
    """Update status file for the dashboard to read."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False)
    except Exception as e:
        log(f"Failed to update status file: {e}", "WARN")

def download_audio(video_id: str, output_path: str) -> bool:
    """Download audio using yt-dlp."""
    log(f"Downloading audio for {video_id}...", "INFO")
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "-f", "m4a/bestaudio/best",
        "--extract-audio",
        "--audio-format", "m4a",
        "--quiet",
        "--no-warnings",
        "-o", output_path,
        url
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Failed to download audio for {video_id}: {e}", "ERR")
        return False

def transcribe_audio_with_gemini(audio_path: str, client: genai.Client) -> list:
    """Upload to Gemini and get JSON transcript."""
    log("Uploading audio to Gemini...", "INFO")
    
    # Upload file
    myfile = client.files.upload(file=audio_path)
    log(f"File uploaded successfully: {myfile.name}", "OK")
    
    prompt = """
    You are an expert transcriptionist. Please transcribe the following Thai speech accurately.
    Return the transcription as a JSON array of objects. 
    Each object MUST have:
    - "text": The spoken text (in Thai). Try to group sentences logically.
    - "start": The start time in seconds (float).
    - "duration": The duration of the text segment in seconds (float).
    
    IMPORTANT: Output ONLY the raw JSON array. Do not use markdown code blocks like ```json.
    """
    
    log("Waiting for Gemini to transcribe...", "INFO")
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[myfile, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            break # Success, break out of retry loop
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "rate limit" in error_str or "exhausted" in error_str:
                wait_time = 60 * (attempt + 1)
                log(f"Rate limit hit! Waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}...", "WARN")
                time.sleep(wait_time)
            else:
                log(f"Failed to transcribe with Gemini: {e}", "ERR")
                # Cleanup file on Google's servers before returning
                try:
                    client.files.delete(name=myfile.name)
                except:
                    pass
                return []
    else:
        log("Max retries reached for Gemini API. Skipping.", "ERR")
        try:
            client.files.delete(name=myfile.name)
        except:
            pass
        return []

    # Cleanup file on Google's servers
    try:
        client.files.delete(name=myfile.name)
    except Exception as e:
        log(f"Failed to delete file from Gemini: {e}", "WARN")
        
    # Parse JSON
    try:
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        
        transcript = json.loads(text.strip())
        return transcript
    except Exception as e:
        log(f"Failed to parse Gemini output: {e}\nRaw output: {response.text[:200]}...", "ERR")
        return []

def get_missing_videos(channel_name: str) -> list:
    """Fetch channel videos and compare with transcribed videos."""
    # 1. Get total channel videos
    log(f"Fetching channel videos for {channel_name}...", "INFO")
    try:
        r = requests.post(f"{API_URL}/api/channel-videos", json={"channel_name": channel_name})
        r.raise_for_status()
        videos = r.json().get("videos", [])
    except Exception as e:
        log(f"Failed to fetch channel videos from backend: {e}", "ERR")
        sys.exit(1)

    # 2. Get transcribed videos
    try:
        r = requests.get(f"{API_URL}/api/transcription-stats")
        r.raise_for_status()
        transcribed_ids = set(r.json().get("transcribed_ids", []))
    except Exception as e:
        log(f"Failed to fetch stats from backend: {e}", "ERR")
        sys.exit(1)

    missing = [v for v in videos if v["id"] not in transcribed_ids]
    return missing

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="@AssabiqoonPublisher", help="Channel handle")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of videos to process (0 = all)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log("GEMINI_API_KEY not found in .env", "ERR")
        sys.exit(1)

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        log(f"Failed to initialize Gemini Client: {e}", "ERR")
        sys.exit(1)

    db_manager = DatabaseManager(Config.CACHE_DIR)
    
    missing_videos = get_missing_videos(args.channel)
    if args.limit > 0:
        missing_videos = missing_videos[:args.limit]

    total = len(missing_videos)
    if total == 0:
        log("No missing videos found. Everything is transcribed!", "OK")
        update_status({"status": "idle", "success_count": 0, "fail_count": 0, "last_updated": time.time()})
        return

    log(f"Found {total} videos missing transcripts.", "INFO")
    
    success = 0
    failed = 0
    temp_audio_dir = os.path.join(Config.CACHE_DIR, "temp_audio")
    os.makedirs(temp_audio_dir, exist_ok=True)

    status = {
        "status": "running",
        "current_index": 0,
        "total_to_process": total,
        "current_video_id": "",
        "current_video_title": "",
        "progress_state": "starting",
        "success_count": 0,
        "fail_count": 0,
        "last_updated": time.time()
    }
    update_status(status)

    for i, video in enumerate(missing_videos, 1):
        vid = video["id"]
        title = video["title"]
        log(f"Processing {i}/{total}: {title} ({vid})", "INFO")
        
        status["current_index"] = i
        status["current_video_id"] = vid
        status["current_video_title"] = title
        status["progress_state"] = "downloading"
        status["last_updated"] = time.time()
        update_status(status)

        audio_path = os.path.join(temp_audio_dir, f"{vid}.m4a")
        
        # Download
        if not download_audio(vid, audio_path):
            failed += 1
            status["fail_count"] = failed
            status["progress_state"] = "download_failed"
            update_status(status)
            continue

        # Transcribe
        status["progress_state"] = "uploading_gemini"
        update_status(status)
        
        transcript = transcribe_audio_with_gemini(audio_path, client)
        
        # Cleanup audio
        if os.path.exists(audio_path):
            os.remove(audio_path)

        if transcript:
            # Save to Database
            status["progress_state"] = "saving"
            update_status(status)
            try:
                db_manager.set_document("transcripts", vid, transcript)
                success += 1
                status["success_count"] = success
                status["progress_state"] = "success"
                log(f"Successfully transcribed and saved {vid}!", "OK")
            except Exception as e:
                failed += 1
                status["fail_count"] = failed
                status["progress_state"] = "save_failed"
                log(f"Failed to save {vid} to database: {e}", "ERR")
        else:
            failed += 1
            status["fail_count"] = failed
            status["progress_state"] = "transcription_failed"
            log(f"Failed to transcribe {vid}.", "ERR")
            
        update_status(status)
        
        # Rate limit protection: Sleep for 30 seconds to prevent hitting the 250k Tokens/Min limit
        log("Sleeping 30 seconds to avoid hitting API rate limits...", "INFO")
        time.sleep(30)

    log(f"Finished! Success: {success}, Failed: {failed}", "OK")
    
    status["status"] = "idle"
    status["progress_state"] = "completed"
    status["last_updated"] = time.time()
    update_status(status)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Process interrupted by user.", "WARN")
        # Update status to stopped
        try:
            with open(STATUS_FILE, "r") as f:
                status = json.load(f)
            status["status"] = "idle"
            status["progress_state"] = "stopped"
            status["last_updated"] = time.time()
            update_status(status)
        except:
            pass
