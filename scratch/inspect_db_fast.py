import os
import sys
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient

client = YouTubeClient()
db = client.db_manager.db

video_ids = ["fKNhhDb-8xs", "A3jk5u8RssQ", "CainbCK5V7M", "0w55YbVf7DE"]
print("Checking Firestore documents...")
for vid in video_ids:
    doc = db.collection("transcripts").document(vid).get()
    if doc.exists:
        data = doc.to_dict()
        transcript_len = len(data.get("data", []))
        print(f"Document {vid}: EXISTS (transcript length: {transcript_len} segments)")
    else:
        print(f"Document {vid}: NOT FOUND")
