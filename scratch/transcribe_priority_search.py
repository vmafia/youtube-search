import os
import sys
import time
import logging
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
    for idx, (vid_id, title) in enumerate(candidate_map.items()):
        logger.info(f"  [{idx+1}] ID: {vid_id} | Title: {title}")
        
    success_count = 0
    skipped_count = 0
    failed_count = 0
    
    for i, (video_id, title) in enumerate(candidate_map.items()):
        # Check if already in DB
        try:
            doc_ref = db.collection("transcripts").document(video_id).get()
            if doc_ref.exists:
                skipped_count += 1
                logger.info(f"[{i+1}/{len(candidate_map)}] Already cached in DB: {video_id}")
                continue
        except Exception as e:
            logger.warning(f"Error checking Firestore for {video_id}: {e}")
            
        logger.info(f"[{i+1}/{len(candidate_map)}] Transcribing candidate video: {video_id} - {title[:40]}...")
        
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
    logger.info(f"Total priority candidates: {len(candidate_map)}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Skipped (already cached): {skipped_count}")
    logger.info(f"Failed: {failed_count}")

if __name__ == "__main__":
    main()
