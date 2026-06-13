import requests
import json
import re

def extract_glasp(video_id):
    url = f'https://glasp.co/reader?url=https://www.youtube.com/watch?v={video_id}'
    r = requests.get(url)
    
    match = re.search(r'\\\"transcripts\\\":(\[.*?\]),\\\"videoId\\\"', r.text)
    if match:
        raw_json = match.group(1).replace('\\\"', '\"')
        try:
            # We just want to see if we can regex the text and start
            segments = re.findall(r'"text":"(.*?)".*?"start":(\d+(?:\.\d+)?)', raw_json)
            print(f'Found {len(segments)} segments via fallback!')
            print(segments[:2])
            return segments
        except Exception as e:
            print('Parse error:', e)
    else:
        print('Regex match failed for', video_id)
        print(r.text.find('transcripts'))
    return None

extract_glasp('QFLm1eQ12oU')
