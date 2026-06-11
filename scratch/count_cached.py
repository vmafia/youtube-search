import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.db import DatabaseManager

def main():
    db_manager = DatabaseManager(os.path.join(base_dir, "backend", "cache"))
    if not db_manager.use_firebase:
        logger.warning("Firebase is not active. Counting local cache instead...")
        # Local JSON cache files
        cache_path = os.path.join(base_dir, "backend", "cache", "transcripts")
        if os.path.exists(cache_path):
            files = [f for f in os.listdir(cache_path) if f.endswith(".json")]
            logger.info(f"Total locally cached transcripts: {len(files)}")
        else:
            logger.info("Local transcripts cache folder does not exist")
        return
        
    db = db_manager.db
    logger.info("Connecting to Firestore to count transcripts...")
    docs = db.collection("transcripts").list_documents()
    count = sum(1 for _ in docs)
    logger.info(f"Total cached transcripts in Firestore: {count}")

if __name__ == "__main__":
    main()
