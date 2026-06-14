import json, gzip

with gzip.open('backend/cache/all_transcripts.json.gz', 'rt', encoding='utf-8') as f:
    data = json.load(f)

segments = data.get('0E2Tv0n84S4', [])
with open('context2.txt', 'w', encoding='utf-8') as out:
    for i, item in enumerate(segments):
        t = item.get('text', '')
        if 'ชีวิตแล้วเนี่ยมีคนอ้างตัวเองเป็นเป็นนบี' in t:
            for j in range(max(0, i-5), min(len(segments), i+15)):
                out.write(f"[{j}]: {segments[j].get('text', '')}\n")
            out.write("------------------------\n")
