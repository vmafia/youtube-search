import os
import sys
import time
import logging
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

# Import client
from backend.utils.youtube import YouTubeClient

def main():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    query = ""
    if len(sys.argv) >= 2 and sys.argv[1].strip() and not any(c in sys.argv[1] for c in ['', '๏', 'ฟ']):
        query = sys.argv[1].strip()
        
    if not query:
        query_file = os.path.join(base_dir, "query.txt")
        if os.path.exists(query_file):
            with open(query_file, "r", encoding="utf-8") as f:
                query = f.read().strip()
                print(f"[*] Read query from query.txt: '{query}'")
                
    if not query:
        print("Usage: python scratch/download_by_query.py '<search_query>' or write it to query.txt")
        sys.exit(1)
    channel_name = "@AssabiqoonPublisher"
    
    print(f"[*] Initializing YouTubeClient...")
    client = YouTubeClient(api_key=os.environ.get("YOUTUBE_API_KEY"))
    
    if not client.db_manager.use_firebase:
        print("[!] Error: Firebase is not initialized. Please verify credentials.")
        sys.exit(1)
        
    print(f"[*] Searching YouTube API for query: '{query}' inside channel: {channel_name}...")
    matched_videos = client.search_youtube_api(channel_name, query, max_results=50)
    
    print(f"[+] Found {len(matched_videos)} videos matching query.")
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, video in enumerate(matched_videos, 1):
        video_id = video["id"]
        title = video["title"]
        
        # Check if already cached
        if client.db_manager.get_document("transcripts", video_id):
            print(f"[{idx}/{len(matched_videos)}] Skipped: {title} ({video_id}) - Already cached.")
            skipped_count += 1
            continue
            
        print(f"[{idx}/{len(matched_videos)}] Downloading: {title} ({video_id})")
        try:
            transcript = client.fetch_video_transcript(video_id)
            if transcript:
                print(f"    [+] Success! Cached {len(transcript)} snippets to Firestore.")
                success_count += 1
            else:
                print(f"    [!] Failed: Returned empty transcript.")
                failed_count += 1
        except Exception as e:
            print(f"    [!] Failed to download: {e}")
            failed_count += 1
            
        time.sleep(2.0)
        
    print("\n==================================================")
    print(f"[+] Download complete!")
    print(f"    Total videos: {len(matched_videos)}")
    print(f"    Successfully cached: {success_count}")
    print(f"    Already cached: {skipped_count}")
    print(f"    Failed: {failed_count}")
    print("==================================================")

if __name__ == "__main__":
    main()
