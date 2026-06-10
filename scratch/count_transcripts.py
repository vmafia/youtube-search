import os
import sys
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient

client = YouTubeClient()
db = client.db_manager.db

try:
    docs = db.collection("transcripts").list_documents()
    count = sum(1 for _ in docs)
    print(f"Total transcripts cached in Firestore: {count}")
except Exception as e:
    print("Error listing documents:", e)
