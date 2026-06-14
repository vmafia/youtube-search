import os
import json
import time
import requests
import concurrent.futures
from backend.utils.db import DatabaseManager
from backend.config import Config

CACHE_DIR = Config.CACHE_DIR
os.makedirs(os.path.join(CACHE_DIR, "transcripts"), exist_ok=True)

def fetch_transcript_from_glasp(video_id):
    url = f"https://glasp.co/reader?url=https://www.youtube.com/watch?v={video_id}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return None
        text = res.text
        idx = text.find('transcripts\\":[')
        if idx != -1:
            end_idx = text.find('}],\\"', idx)
            if end_idx != -1:
                array_str = text[idx+14:end_idx+2]
            else:
                array_str = text[idx+14:text.find(']', idx)+1]
            clean_str = array_str.replace('\\"', '"').replace('\\\\n', '\\n').replace('\\n', ' ')
            try:
                data = json.loads(clean_str)
                segments = [{"start": item.get('start', 0), "duration": item.get('duration', 0), "text": item.get('text', '')} for item in data]
                return segments
            except:
                return None
        else:
            idx = text.find('"transcripts":[')
            if idx != -1:
                array_str = text[idx+14:text.find(']', idx)+1]
                try:
                    data = json.loads(array_str)
                    return data
                except:
                    return None
            return None
    except:
        return None

def process_video(vid):
    local_path = os.path.join(CACHE_DIR, "transcripts", f"{vid}.json")
    if os.path.exists(local_path):
        return "cached"
    
    transcript = fetch_transcript_from_glasp(vid)
    if transcript:
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)
            return "success"
        except:
            return "error"
    return "failed"

def main():
    print("Loading channel videos...")
    cv_dir = os.path.join(CACHE_DIR, "channel_videos")
    if not os.path.exists(cv_dir):
        print("No channel videos cache found!")
        return
        
    files = [f for f in os.listdir(cv_dir) if f.endswith('.json')]
    if not files:
        print("No channel videos JSON found!")
        return
        
    files.sort(key=lambda x: os.path.getsize(os.path.join(cv_dir, x)), reverse=True)
    with open(os.path.join(cv_dir, files[0]), 'r', encoding='utf-8') as f:
        videos = json.load(f)
        
    vids = [v['id'] for v in videos]
    print(f"Found {len(vids)} videos to process.")
    
    success_count = 0
    cached_count = 0
    failed_count = 0
    
    # Process with 10 threads for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_video, vid): vid for vid in vids}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            if res == "success":
                success_count += 1
            elif res == "cached":
                cached_count += 1
            else:
                failed_count += 1
                
            if i % 100 == 0 or i == len(vids):
                print(f"Progress: {i}/{len(vids)} | Saved: {success_count} | Cached: {cached_count} | No CC: {failed_count}")
                
    print(f"\nDone! Successfully saved {success_count} new transcripts to local disk.")

if __name__ == "__main__":
    main()
