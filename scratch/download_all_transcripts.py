import os
import sys
import time
from dotenv import load_dotenv

# Add backend directory to path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient
from backend.config import Config

def main():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    channel_name = "@AssabiqoonPublisher"
    args = [arg for arg in sys.argv[1:] if arg not in ("--yes", "-y")]
    if args:
        channel_name = args[0].strip()
        
    print(f"[*] Initializing YouTubeClient...")
    client = YouTubeClient(api_key=Config.YOUTUBE_API_KEY, cache_dir=Config.CACHE_DIR)
    
    print(f"[*] Fetching list of all videos for channel: {channel_name}...")
    try:
        # Fetch up to 5000 videos (the limit can be adjusted)
        videos = client.fetch_channel_videos(channel_name, limit=5000)
    except Exception as e:
        print(f"[!] Failed to fetch channel videos list: {e}")
        sys.exit(1)
        
    total_videos = len(videos)
    print(f"[+] Found {total_videos} videos in channel.")
    
    # Check what is already cached using bulk ID checking
    print(f"[*] Fetching cached transcript list from database...")
    cached_ids = set(client.db_manager.get_all_document_ids("transcripts"))
    
    cached_count = 0
    to_download = []
    
    for idx, video in enumerate(videos, 1):
        video_id = video["id"]
        # Check if transcript already exists in cache (O(1) set lookup)
        if video_id in cached_ids:
            cached_count += 1
        else:
            to_download.append(video)
            
    print(f"[*] Current status: {cached_count}/{total_videos} transcripts are already cached.")
    print(f"[*] Need to download {len(to_download)} transcripts.")
    
    if not to_download:
        print("[+] All transcripts are already cached! Nothing to do.")
        return
        
    # Warn user about cookies
    cookies_path = os.path.join(base_dir, "cookies.txt")
    if not os.path.exists(cookies_path):
        print("\n[!] WARNING: cookies.txt is not found in the root directory.")
        print("    YouTube might rate-limit or block this script after a few videos.")
        print("    It is highly recommended to Export cookies.txt from your browser to bypass blocks.")
        if "--yes" in sys.argv or "-y" in sys.argv:
            print("[*] Continuing anyway because --yes flag is set.")
        else:
            response = input("Do you want to continue anyway? (y/n): ").strip().lower()
            if response != 'y':
                print("Aborted.")
                return
            
    print("\n[*] Starting downloads...")
    success_count = 0
    failed_count = 0
    
    for idx, video in enumerate(to_download, 1):
        video_id = video["id"]
        title = video["title"]
        print(f"\n[{idx}/{len(to_download)}] Downloading: {title} ({video_id})")
        
        try:
            # fetch_video_transcript will automatically save it to cache if successful
            transcript = client.fetch_video_transcript(video_id)
            if transcript:
                print(f"    [+] Success! Cached {len(transcript)} snippets.")
                success_count += 1
            else:
                print(f"    [!] Failed: Returned empty transcript.")
                failed_count += 1
        except Exception as e:
            print(f"    [!] Failed to download: {e}")
            failed_count += 1
            
        # Polite delay to prevent getting blocked
        time.sleep(2.0)
        
    print("\n==================================================")
    print(f"[+] Download session complete!")
    print(f"    Total videos attempted: {len(to_download)}")
    print(f"    Successfully cached: {success_count}")
    print(f"    Failed: {failed_count}")
    print(f"    Total cached transcripts now: {cached_count + success_count}/{total_videos}")
    print("==================================================")

if __name__ == "__main__":
    main()
