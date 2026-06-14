import json, gzip, time, os
from backend.utils.search import normalize_text

start = time.time()
with gzip.open('backend/cache/all_transcripts.json.gz', 'rt', encoding='utf-8') as f:
    data = json.load(f)

for vid, segments in data.items():
    for item in segments:
        item['norm_text'] = normalize_text(item.get('text', ''))

with gzip.open('backend/cache/all_transcripts.json.gz', 'wt', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

print(f"size: {os.path.getsize('backend/cache/all_transcripts.json.gz')/1024/1024:.2f} MB")
print(f"Time: {time.time()-start:.2f}s")
