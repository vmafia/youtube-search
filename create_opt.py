import json, gzip, time, os
from backend.utils.search import normalize_text

start = time.time()
with gzip.open('backend/cache/all_transcripts.json.gz', 'rt', encoding='utf-8') as f:
    data = json.load(f)

text_only = {}
for vid, segments in data.items():
    text_only[vid] = ' '.join(normalize_text(s.get('text', '')) for s in segments)

with gzip.open('backend/cache/search_optimized.json.gz', 'wt', encoding='utf-8') as f:
    json.dump(text_only, f, ensure_ascii=False)

print(f"size: {os.path.getsize('backend/cache/search_optimized.json.gz')/1024/1024:.2f} MB")
