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
        logger.error("Firebase is not initialized.")
        return
        
    db = db_manager.db
    docs = db.collection("transcripts").list_documents()
    print("Cached document IDs in Firestore (transcripts):")
    for idx, doc in enumerate(docs):
        # Retrieve the document data if we want to print content count
        data = doc.get().to_dict()
        lines_count = len(data) if isinstance(data, list) else 0
        print(f"  [{idx+1}] ID: {doc.id} | Segments: {lines_count}")
        if idx >= 15:
            print("  ... and more")
            break

if __name__ == "__main__":
    main()
