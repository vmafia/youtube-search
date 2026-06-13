import requests
import json
url = 'https://glasp.co/reader?url=https://www.youtube.com/watch?v=-CtWUPy0J9Q'
res = requests.get(url)
text = res.text
idx = text.find('transcripts\\":[')
if idx != -1:
    end_idx = text.find('}],\\"', idx)
    if end_idx != -1:
        array_str = text[idx+14:end_idx+2]
    else:
        array_str = text[idx+14:text.find(']', idx)+1]
    
    print('RAW:', array_str[:200])
    clean_str = array_str.replace('\\"', '"').replace('\\\\n', '\\n').replace('\\n', ' ')
    try:
        data = json.loads(clean_str)
        print('SUCCESS PARSE')
    except Exception as e:
        print('PARSE ERROR:', e)
else:
    print('NOT FOUND transcripts\\\\":[')
    
    # Try the unescaped version
    idx = text.find('"transcripts":[')
    if idx != -1:
        print('FOUND UNESCAPED')
        end_idx = text.find('}],"', idx)
        if end_idx != -1:
            array_str = text[idx+14:end_idx+2]
            print('RAW:', array_str[:200])
            try:
                data = json.loads(array_str)
                print('SUCCESS PARSE UNESCAPED')
            except Exception as e:
                print('PARSE ERROR:', e)
