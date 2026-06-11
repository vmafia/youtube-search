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
for doc in docs:
    data = doc.get().to_dict()
    print(f"Document ID: {doc.id}")
    # Print first few elements of data if it is a dict or list
    if data:
        items = data.get("data", [])
        if items and isinstance(items, list):
            print("First 3 items of transcript:")
            for item in items[:3]:
                print(item)
        else:
            print("Data is not list:", str(data)[:200])
    print("-" * 50)
