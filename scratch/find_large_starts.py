import os
import json

cache_dir = r"C:\Users\hp\Documents\GitHub\youtube-search\backend\cache\transcripts"
for filename in os.listdir(cache_dir):
    if filename.endswith(".json"):
        path = os.path.join(cache_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    starts = [item.get("start", 0) for item in data]
                    max_start = max(starts) if starts else 0
                    if max_start > 1000:
                        print(f"{filename}: max start = {max_start}")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
