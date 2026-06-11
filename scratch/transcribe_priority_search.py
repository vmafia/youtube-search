import os
import sys
import time
import logging
import re
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

if os.path.exists("D:\\"):
    d_drive_temp = "D:\\youtube_search_temp"
    d_drive_hf = "D:\\huggingface_cache"
else:
    d_drive_temp = os.path.join(base_dir, "scratch", "temp_subs")
    d_drive_hf = os.path.join(base_dir, "scratch", "huggingface_cache")

os.environ["HF_HOME"] = d_drive_hf

from backend.utils.youtube import YouTubeClient
from scratch.download_yt_dlp import download_subs_api, download_subs_yt_dlp, download_audio_and_transcribe

def parse_iso8601_duration(duration_str):
    # e.g. PT1H21M16S or PT45S or PT5M
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration_str)
    if not match:
        return 0
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return hours * 3600 + minutes * 60 + seconds

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized. Please verify credentials.")
        sys.exit(1)
        
    db = client.db_manager.db
    channel_name = "@AssabiqoonPublisher"
    
    # We query the YouTube Search API for the terms searched by the user
    queries = ["มุซัยละฮฺ อัล-กัซซาบ", "ทางรอด"]
    candidate_map = {}
    
    for q in queries:
        logger.info(f"Querying YouTube Search API for term: '{q}'...")
        vids = client.search_youtube_api(channel_name, q, max_results=50)
        logger.info(f"Found {len(vids)} candidates for query '{q}'.")
        for v in vids:
            candidate_map[v["id"]] = v["title"]
            
    logger.info(f"Total unique priority candidate videos found: {len(candidate_map)}")
    
    # Fetch durations and sort candidates by duration (shortest first)
    logger.info("Fetching durations for all candidate videos...")
    video_ids = list(candidate_map.keys())
    durations = {}
    
    # Batch query in chunks of 50
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        ids_str = ",".join(chunk)
        url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={ids_str}&key={api_key}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                items = r.json().get("items", [])
                for item in items:
                    vid_id = item["id"]
                    duration_str = item["contentDetails"]["duration"]
                    durations[vid_id] = parse_iso8601_duration(duration_str)
        except Exception as e:
            logger.warning(f"Failed to fetch durations for chunk {i}: {e}")
            
    # Sort candidates: shortest first. Default duration is 999999 for failures.
    sorted_candidates = sorted(
        candidate_map.items(),
        key=lambda x: durations.get(x[0], 999999)
    )
    
    logger.info("Priority candidate list (sorted by duration):")
    for idx, (vid_id, title) in enumerate(sorted_candidates):
        dur = durations.get(vid_id, 0)
        logger.info(f"  [{idx+1}] ID: {vid_id} | Duration: {format_duration(dur)} | Title: {title}")
        
    success_count = 0
    skipped_count = 0
    failed_count = 0
    
    for i, (video_id, title) in enumerate(sorted_candidates):
        dur = durations.get(video_id, 0)
        # Check if already in DB
        try:
            doc_ref = db.collection("transcripts").document(video_id).get()
            if doc_ref.exists:
                skipped_count += 1
                logger.info(f"[{i+1}/{len(sorted_candidates)}] Already cached in DB: {video_id} ({format_duration(dur)})")
                continue
        except Exception as e:
            logger.warning(f"Error checking Firestore for {video_id}: {e}")
            
        logger.info(f"[{i+1}/{len(sorted_candidates)}] Transcribing candidate video: {video_id} ({format_duration(dur)}) - {title[:40]}...")
        
        # 1. Try standard API
        transcript = download_subs_api(video_id)
        
        # 2. Try yt-dlp subtitles
        if not transcript:
            transcript = download_subs_yt_dlp(video_id)
            
        # 3. Fallback to Whisper
        if not transcript:
            transcript = download_audio_and_transcribe(video_id)
            
        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                success_count += 1
                logger.info(f"-> Successfully cached transcript for candidate video {video_id}")
            except Exception as e:
                logger.error(f"-> Failed to write transcript to DB: {e}")
        else:
            logger.warning(f"-> Failed to transcribe candidate video {video_id}")
            failed_count += 1
            
        # Mild pause to avoid rate limits
        time.sleep(2.0)
        
    logger.info("========================================")
    logger.info("Candidate priority transcription completed!")
    logger.info(f"Total priority candidates: {len(sorted_candidates)}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Skipped (already cached): {skipped_count}")
    logger.info(f"Failed: {failed_count}")

if __name__ == "__main__":
    main()
