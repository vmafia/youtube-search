import os
import sys
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

# Initialize Firebase
cred_path = os.path.join(base_dir, "backend", "firebase-credentials.json")
if not os.path.exists(cred_path):
    logger.error(f"Credentials not found at {cred_path}")
    sys.exit(1)

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    'projectId': 'transcript-search-b162c'
})
db = firestore.client()

CHANNEL_NAME = "@AssabiqoonPublisher"
LIMIT = 50

def seed_database():
    logger.info(f"Starting seeding for channel {CHANNEL_NAME}...")
    
    # 1. Fetch channel videos using scrapetube
    url = f"https://www.youtube.com/{CHANNEL_NAME}"
    logger.info(f"Fetching latest {LIMIT} videos from {url}...")
    
    videos = []
    try:
        generator = scrapetube.get_channel(channel_url=url, limit=LIMIT)
        for v in generator:
            video_id = v["videoId"]
            title = v.get("title", {}).get("runs", [{}])[0].get("text", "Untitled Video")
            published_text = v.get("publishedTimeText", {}).get("simpleText", "Recently")
            
            videos.append({
                "id": video_id,
                "title": title,
                "published_at": published_text,
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            })
    except Exception as e:
        logger.error(f"Failed to scrape channel videos: {str(e)}")
        return

    if not videos:
        logger.warning("No videos found. Exiting.")
        return

    logger.info(f"Successfully retrieved {len(videos)} videos.")

    # Write the channel videos list to Firestore
    cache_key = f"channel_videos_{CHANNEL_NAME}_{100}" # Match default limit
    db.collection("channel_videos").document(cache_key).set({"data": videos})
    logger.info(f"Stored channel videos list in Firestore under key: {cache_key}")

    # 2. Fetch transcripts and write to Firestore
    success_count = 0
    for idx, video in enumerate(videos):
        video_id = video["id"]
        title = video["title"]
        logger.info(f"[{idx+1}/{len(videos)}] Fetching transcript for video: {video_id} ({title[:30]}...)")
        
        transcript = None
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"No direct th/en transcripts for {video_id}, trying listing fallback...")
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = transcript_list.find_transcript(["th", "en"]).fetch()
            except Exception as inner_e:
                logger.warning(f"Failed to fetch transcript for {video_id}: {str(inner_e)}")
        except Exception as e:
            logger.warning(f"Error fetching transcript for {video_id}: {str(e)}")

        if transcript:
            # Save to Firestore
            db.collection("transcripts").document(video_id).set({"data": transcript})
            logger.info(f"-> Successfully saved transcript for {video_id} to Firestore")
            success_count += 1
        else:
            logger.warning(f"-> Skipping {video_id} (No transcript available)")

    logger.info(f"Seeding completed. Successfully uploaded transcripts for {success_count}/{len(videos)} videos.")

if __name__ == "__main__":
    seed_database()
