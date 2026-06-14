import json, gzip

with gzip.open('backend/cache/all_transcripts.json.gz', 'rt', encoding='utf-8') as f:
    data = json.load(f)

segments = data.get('-slvKBuryqo', [])
with open('context.txt', 'w', encoding='utf-8') as out:
    for i, item in enumerate(segments):
        t = item.get('text', '')
        if 'อ้างว่ามันเป็นนบี' in t or 'เลื่อนสถานะ' in t:
            for j in range(max(0, i-10), min(len(segments), i+10)):
                out.write(f"[{j}]: {segments[j].get('text', '')}\n")
            out.write("------------------------\n")
