import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized.")
        return
        
    db = client.db_manager.db
    queries = ["มุซัยละฮฺ อัล-กัซซาบ", "ทางรอด"]
    candidate_ids = []
    
    for q in queries:
        vids = client.search_youtube_api("@AssabiqoonPublisher", q, max_results=50)
        for v in vids:
            if v["id"] not in candidate_ids:
                candidate_ids.append(v["id"])
                
    logger.info(f"Total candidates from API: {len(candidate_ids)}")
    
    cached_count = 0
    missing_ids = []
    
    for vid_id in candidate_ids:
        doc = db.collection("transcripts").document(vid_id).get()
        if doc.exists:
            cached_count += 1
        else:
            missing_ids.append(vid_id)
            
    logger.info(f"Cached candidates: {cached_count}/{len(candidate_ids)}")
    logger.info(f"Missing candidate IDs: {missing_ids}")

if __name__ == "__main__":
    main()
