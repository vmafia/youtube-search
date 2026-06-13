import requests
import re
import json

url = 'https://glasp.co/reader?url=https://www.youtube.com/watch?v=-6snnMTz4Hk'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
res = requests.get(url, headers=headers)
res.encoding = 'utf-8'

text = res.text
idx = text.find('transcripts\\":[')
if idx != -1:
    print('FOUND AT', idx)
    print(text[idx:idx+300])
    
    # Try parsing the array using regex
    import ast
    # Extract the array string
    array_str = text[idx+14:text.find(']', idx)+1]
    # The string looks like [{\"start\":0,\"text\":\"เดี๋ยวผมจะพูดอย่างนี้นะครับว่าดีเด้อเรา มา\\nตอนเนี้ยปิดเดือนแห่งการเปลี่ยนแปลง แล้วก็ผม\\nคิดว่าครับเดือนนี้เรายังเปลี่ยน\"},...]
    # It has escaped quotes and backslashes.
    try:
        # Replace escaped quotes with normal quotes
        clean_str = array_str.replace('\\"', '"').replace('\\\\n', '\n')
        data = json.loads(clean_str)
        print('Parsed successfully!', len(data))
        print(data[:2])
    except Exception as e:
        print('JSON error:', e)
        print(clean_str[:200])
