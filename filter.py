import json
with open('scratch_fake_prophet.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

matches = []
for item in data:
    t = item['text']
    if 'อ้าง' in t or 'ปลอม' in t or 'กัซ' in t or 'ซัย' in t or 'สัย' in t:
        matches.append(item)

with open('scratch_final.json', 'w', encoding='utf-8') as out:
    json.dump(matches, out, ensure_ascii=False, indent=2)
