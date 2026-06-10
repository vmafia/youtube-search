import os
import sys
import logging
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths and import modules
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

# Import YouTube client
from backend.utils.youtube import YouTubeClient

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not found in environment")
        sys.exit(1)
        
    # Initialize YouTube client (which automatically initializes Firebase Admin SDK under the hood)
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized. Please verify your credentials.")
        sys.exit(1)
        
    channel_name = "@AssabiqoonPublisher"
    limit = 5000
    
    logger.info(f"Fetching up to {limit} videos for channel {channel_name}...")
    try:
        # Fetch from YouTube API directly
        videos = client._fetch_via_api(channel_name, limit)
        logger.info(f"Successfully fetched {len(videos)} videos from YouTube API")
        
        # Save to Firestore and local cache using DatabaseManager
        cache_key = f"channel_videos_{channel_name}_{limit}"
        client.db_manager.set_document("channel_videos", cache_key, videos)
        logger.info(f"Successfully cached {len(videos)} videos to Firestore and local cache under: {cache_key}")
        
        # Also cache it under the 100 limit key
        cache_key_100 = f"channel_videos_{channel_name}_100"
        client.db_manager.set_document("channel_videos", cache_key_100, videos[:100])
        logger.info("Also cached first 100 videos under: channel_videos_@AssabiqoonPublisher_100")
        
    except Exception as e:
        logger.error(f"Error occurred during fetch/cache process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
