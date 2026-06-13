import sys
import os
import time
import requests
import re
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.utils.youtube import YouTubeClient
from dotenv import load_dotenv

load_dotenv()

def fetch_transcript_from_glasp(video_id):
    url = f"https://glasp.co/reader?url=https://www.youtube.com/watch?v={video_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        if res.status_code != 200:
            print(f"[{video_id}] Error {res.status_code}")
            return None
            
        text = res.text
        idx = text.find('transcripts\\":[')
        if idx != -1:
            end_idx = text.find('}],\\"', idx)
            if end_idx != -1:
                array_str = text[idx+14:end_idx+2]
            else:
                array_str = text[idx+14:text.find(']', idx)+1] # Fallback
            clean_str = array_str.replace('\\"', '"').replace('\\\\n', '\\n').replace('\\n', ' ')
            try:
                data = json.loads(clean_str)
                segments = []
                for item in data:
                    segments.append({
                        "start": item.get('start', 0),
                        "duration": item.get('duration', 0),
                        "text": item.get('text', '')
                    })
                return segments
            except Exception as e:
                print(f"[{video_id}] JSON Parse Error: {e}")
                return None
        else:
            # Fallback if not escaped
            idx = text.find('"transcripts":[')
            if idx != -1:
                array_str = text[idx+14:text.find(']', idx)+1]
                try:
                    data = json.loads(array_str)
                    return data
                except Exception as e:
                    print(f"[{video_id}] JSON Parse Error (fallback): {e}")
            return None
    except Exception as e:
        print(f"[{video_id}] Request failed: {e}")
        return None

def main():
    client = YouTubeClient('firebase')
    
    print("Fetching videos to scrape from Firebase...")
    docs = client.db_manager.db.collection('transcripts').stream()
    videos_to_scrape = []
    for doc in docs:
        data = doc.to_dict()
        if 'segments' not in data or not data['segments']:
            videos_to_scrape.append(doc.id)
            
    print(f"Found {len(videos_to_scrape)} videos to scrape via Glasp.")
    if not videos_to_scrape:
        print("Everything is already scraped!")
        return
        
    count = 0
    success = 0
    for vid in videos_to_scrape:
        count += 1
        print(f"--- Scraping {count}/{len(videos_to_scrape)} : {vid} ---")
        transcript = fetch_transcript_from_glasp(vid)
        
        doc_ref = client.db_manager.db.collection('transcripts').document(vid)
        if transcript:
            try:
                print(f"[{vid}] Success! Saving {len(transcript)} segments to Firebase...")
                doc_ref.set({"segments": transcript}, merge=True)
                success += 1
            except Exception as e:
                if "exceeds the maximum allowed size" in str(e) or "InvalidArgument" in str(e) or "400" in str(e):
                    print(f"[{vid}] Document too large! Truncating to first 8000 segments...")
                    try:
                        # 8000 segments is roughly 10-12 hours of video and should safely fit under 1MB
                        doc_ref.set({"segments": transcript[:8000]}, merge=True)
                        success += 1
                        print(f"[{vid}] Truncated and saved successfully.")
                    except Exception as e2:
                        print(f"[{vid}] Still failed after truncating: {e2}")
                        doc_ref.set({"scrape_status": "failed_too_large"}, merge=True)
                else:
                    print(f"[{vid}] Failed to save to Firebase: {e}")
        else:
            print(f"[{vid}] No transcript found or failed. Marking as failed/unavailable.")
            doc_ref.set({"scrape_status": "failed_or_unavailable"}, merge=True)
            
        # Brief pause to avoid rate limiting from Glasp
        time.sleep(1)
        
    print(f"Finished scraping all videos! Success: {success}/{len(videos_to_scrape)}")

if __name__ == "__main__":
    main()
