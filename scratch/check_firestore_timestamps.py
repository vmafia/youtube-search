import os
import sys
from dotenv import load_dotenv

base_dir = r"C:\Users\hp\Documents\GitHub\youtube-search"
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.db import DatabaseManager

db_manager = DatabaseManager(os.path.join(base_dir, "backend", "cache"))
if not db_manager.use_firebase:
    print("Firebase not initialized!")
    sys.exit(1)

db = db_manager.db
docs = db.collection("transcripts").stream()
count = 0
for doc in docs:
    data = doc.to_dict().get("data")
    if isinstance(data, list) and len(data) > 0:
        starts = [item.get("start", 0) for item in data]
        max_start = max(starts) if starts else 0
        # If max_start is > 100000 (which is 100 seconds if in ms, but 27 hours if in seconds)
        # Usually videos aren't > 27 hours, so if it's > 100000 it is highly likely in ms.
        # Let's print anything with max_start > 20000
        if max_start > 20000:
            print(f"Firestore doc {doc.id}: max start = {max_start} (length: {len(data)})")
            # print first few items
            print(f"First 5: {data[:5]}")
            count += 1

print(f"Done. Found {count} documents with large start times.")
