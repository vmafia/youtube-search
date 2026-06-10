import os
import sys
import time
import subprocess
import glob
import re
import logging
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

from backend.utils.youtube import YouTubeClient

def parse_time(t_str):
    try:
        t_str = t_str.strip().replace(',', '.')
        parts = t_str.split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m = int(parts[0])
            s = float(parts[1])
            return m * 60 + s
    except Exception as e:
        logger.error(f"Error parsing time string '{t_str}': {e}")
    return 0.0

def parse_vtt(file_path):
    transcript = []
    if not os.path.exists(file_path):
        return None
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Split by blocks (empty lines)
        blocks = re.split(r'\n\s*\n', content)
        
        for block in blocks:
            lines = block.strip().split('\n')
            if not lines:
                continue
                
            # Find timestamp line
            timestamp_idx = -1
            for idx, line in enumerate(lines):
                if '-->' in line:
                    timestamp_idx = idx
                    break
                    
            if timestamp_idx == -1:
                continue
                
            # Parse timestamps
            times = lines[timestamp_idx].split('-->')
            if len(times) != 2:
                continue
                
            start = parse_time(times[0])
            end = parse_time(times[1])
            duration = max(0.0, end - start)
            
            # Extract text
            text_lines = lines[timestamp_idx+1:]
            
            # Filter out empty lines or VTT style tags like <c>
            text = " ".join([re.sub(r'<[^>]+>', '', l).strip() for l in text_lines if l.strip()])
            
            if text:
                transcript.append({
                    "text": text,
                    "start": start,
                    "duration": duration
                })
        return transcript
    except Exception as e:
        logger.error(f"Failed to parse VTT file {file_path}: {e}")
        return None

def download_subs_yt_dlp(video_id):
    temp_dir = os.path.join(base_dir, "scratch", "temp_subs")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Define output template for yt-dlp
    output_tmpl = os.path.join(temp_dir, f"{video_id}")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    # We call yt-dlp using python module to ensure it runs correctly
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--write-auto-subs",
        "--write-subs",
        "--skip-download",
        "--sub-langs", "th",
        "--sub-format", "vtt",
        "--quiet",
        "-o", output_tmpl,
        video_url
    ]
    
    try:
        # Run yt-dlp
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Look for the downloaded subtitle file
        pattern = os.path.join(temp_dir, f"{video_id}.*vtt")
        matches = glob.glob(pattern)
        
        if matches:
            sub_file = matches[0]
            transcript = parse_vtt(sub_file)
            
            # Clean up files
            try:
                os.remove(sub_file)
            except Exception:
                pass
                
            return transcript
    except Exception as e:
        logger.debug(f"yt-dlp command failed for {video_id}: {e}")
        
    return None

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized. Please verify credentials.")
        sys.exit(1)
        
    db = client.db_manager.db
    channel_name = "@AssabiqoonPublisher"
    limit = 5000
    
    # 1. Retrieve the list of channel videos from Firestore
    cache_key = f"channel_videos_{channel_name}_{limit}"
    videos_doc = db.collection("channel_videos").document(cache_key).get()
    
    if not videos_doc.exists:
        logger.error("Channel videos cache not found in Firestore.")
        sys.exit(1)
        
    videos = videos_doc.to_dict().get("data", [])
    logger.info(f"Loaded {len(videos)} videos from channel videos cache.")
    
    success_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Batch process transcripts using yt-dlp
    for i, video in enumerate(videos):
        video_id = video["id"]
        title = video["title"]
        
        # 2. Check if transcript is already cached in Firestore
        try:
            doc_ref = db.collection("transcripts").document(video_id).get()
            if doc_ref.exists:
                skipped_count += 1
                if skipped_count % 100 == 0 or skipped_count == 1:
                    logger.info(f"Progress: [{i+1}/{len(videos)}] - Already cached: {video_id} (Total skipped: {skipped_count})")
                continue
        except Exception as e:
            logger.warning(f"Error checking Firestore for {video_id}: {e}")
            
        logger.info(f"[{i+1}/{len(videos)}] Fetching transcript via yt-dlp for: {video_id} - {title[:40]}...")
        
        # 3. Fetch transcript from YouTube
        transcript = download_subs_yt_dlp(video_id)
        
        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                success_count += 1
                logger.info(f"-> Successfully cached transcript for {video_id} ({len(transcript)} lines)")
            except Exception as e:
                logger.error(f"-> Failed to write transcript to DB: {e}")
        else:
            logger.warning(f"-> Subtitles unavailable/could not download for {video_id}")
            failed_count += 1
            
        # Mild pause to be polite
        time.sleep(0.5)
        
    logger.info("========================================")
    logger.info("yt-dlp Transcript downloading completed!")
    logger.info(f"Total processed: {len(videos)}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Skipped (already cached): {skipped_count}")
    logger.info(f"Failed / Unavailable: {failed_count}")

if __name__ == "__main__":
    main()
