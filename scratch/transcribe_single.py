import os
import sys
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from youtube_transcript_api import YouTubeTranscriptApi
from backend.utils.db import DatabaseManager

video_id = "0w55YbVf7DE"
cookies_path = os.path.join(base_dir, "cookies_new.txt")

try:
    print(f"Attempting to fetch transcript for video: {video_id}...")
    
    # Try fetching with cookies_new.txt
    if os.path.exists(cookies_path):
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
    else:
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
        
    print(f"Successfully retrieved {len(fetched)} transcript segments!")
    print("First 3 segments:", fetched[:3])
    
    # Write to Firestore cache
    db_manager = DatabaseManager("backend/cache")
    db_manager.set_document("transcripts", video_id, fetched)
    print("Transcript successfully written to Firestore!")
    
except Exception as e:
    print(f"Failed to fetch/cache transcript: {e}")
