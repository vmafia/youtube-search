import os
import sys
import time
import logging
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

# Import clients and dependencies
from backend.utils.youtube import YouTubeClient
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized. Please verify credentials.")
        sys.exit(1)
        
    db = client.db_manager.db
    channel_name = "@AssabiqoonPublisher"
    limit = 5000
    
    # 1. Retrieve the list of channel videos from Firestore cache
    cache_key = f"channel_videos_{channel_name}_{limit}"
    videos_doc = db.collection("channel_videos").document(cache_key).get()
    
    if not videos_doc.exists:
        logger.error("Channel videos cache not found in Firestore. Please run fetch_and_cache_all.py first.")
        sys.exit(1)
        
    videos = videos_doc.to_dict().get("data", [])
    logger.info(f"Loaded {len(videos)} videos from channel videos cache.")
    
    success_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Batch process transcripts
    for i, video in enumerate(videos):
        video_id = video["id"]
        title = video["title"]
        
        # 2. Check if transcript is already cached in Firestore
        try:
            doc_ref = db.collection("transcripts").document(video_id).get()
            if doc_ref.exists:
                skipped_count += 1
                if skipped_count % 100 == 0 or skipped_count == 1:
                    logger.info(f"Progress: [{i+1}/{len(videos)}] - Already cached: {video_id} (Total skipped: {skipped_count})")
                continue
        except Exception as e:
            logger.warning(f"Error checking Firestore for {video_id}: {e}")
            
        logger.info(f"[{i+1}/{len(videos)}] Fetching transcript for: {video_id} - {title[:40]}...")
        
        # 3. Fetch transcript from YouTube
        transcript = None
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"-> Transcripts disabled/not found for {video_id}: {e}")
            failed_count += 1
        except Exception as e:
            logger.error(f"-> Rate limit or unexpected error for {video_id}: {e}")
            logger.info("Sleeping for 10 seconds to cool down...")
            time.sleep(10)
            failed_count += 1
            
        # 4. Save to Firestore and Local Cache if found
        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                success_count += 1
                logger.info(f"-> Successfully cached transcript for {video_id}")
            except Exception as e:
                logger.error(f"-> Failed to write transcript to DB: {e}")
                
        # Sleep to avoid aggressive YouTube scraping blocks
        time.sleep(1.0)
        
    logger.info("========================================")
    logger.info("Transcript downloading completed!")
    logger.info(f"Total processed: {len(videos)}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Skipped (already cached): {skipped_count}")
    logger.info(f"Failed / Unavailable: {failed_count}")

if __name__ == "__main__":
    main()
