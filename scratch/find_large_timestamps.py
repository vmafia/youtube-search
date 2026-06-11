import os
import sys
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient

client = YouTubeClient()
db = client.db_manager.db

docs = db.collection("transcripts").list_documents()
found_any = False
for doc_ref in docs:
    doc = doc_ref.get()
    data = doc.to_dict()
    if data:
        items = data.get("data", [])
        if items and isinstance(items, list):
            for idx, item in enumerate(items):
                start = item.get("start", 0)
                if start > 10000:
                    print(f"Video {doc_ref.id} has large start value at index {idx}: {start} (text: {item.get('text')})")
                    found_any = True
                    break
if not found_any:
    print("No large start values found in Firestore transcripts.")
