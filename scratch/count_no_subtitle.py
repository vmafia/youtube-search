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
    client = YouTubeClient()
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not active.")
        return
        
    db = client.db_manager.db
    logger.info("Connecting to Firestore to count transcripts and no_subtitle markers...")
    
    docs = db.collection("transcripts").stream()
    
    total = 0
    no_sub = 0
    has_sub = 0
    
    for doc in docs:
        total += 1
        data = doc.to_dict()
        if isinstance(data, dict) and data.get("no_subtitle") is True:
            no_sub += 1
        else:
            has_sub += 1
            
    logger.info("=" * 40)
    logger.info(f"Total documents in transcripts: {total}")
    logger.info(f"Has subtitle: {has_sub}")
    logger.info(f"No subtitle (marked for Phase 2): {no_sub}")
    logger.info("=" * 40)

if __name__ == "__main__":
    main()
