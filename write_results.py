import json
with open('scratch_final.json', 'r', encoding='utf-8') as f:
    matches = json.load(f)

with open('results.txt', 'w', encoding='utf-8') as out:
    for item in matches:
        t = item['text']
        if 'นบีปลอม' in t or 'อ้าง' in t:
            out.write(f"[{item['vid']}]: {t}\n")
