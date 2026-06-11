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

# Check if Drive D exists, else fallback to base_dir
if os.path.exists("D:\\"):
    d_drive_temp = "D:\\youtube_search_temp"
    d_drive_hf = "D:\\huggingface_cache"
else:
    d_drive_temp = os.path.join(base_dir, "scratch", "temp_subs")
    d_drive_hf = os.path.join(base_dir, "scratch", "huggingface_cache")

# Redirect Hugging Face cache to D Drive to save space on C Drive
os.environ["HF_HOME"] = d_drive_hf
os.makedirs(d_drive_temp, exist_ok=True)
os.makedirs(d_drive_hf, exist_ok=True)

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
    temp_dir = d_drive_temp
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
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--quiet",
        "-o", output_tmpl
    ]
    
    # Use cookies.txt if available to bypass 429 blocks
    cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
        
    cmd.append(video_url)
    
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

# Global whisper model cache
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        logger.info("Initializing faster-whisper model ('base'). This will download the model weights on first run...")
        import torch
        from faster_whisper import WhisperModel
        device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            if device == "cuda":
                # float16 is faster and uses less memory on Nvidia GPU
                _whisper_model = WhisperModel("base", device="cuda", compute_type="float16")
                logger.info("Whisper model loaded successfully on Nvidia CUDA GPU")
            else:
                _whisper_model = WhisperModel("base", device="cpu", compute_type="float32")
                logger.info("Whisper model loaded successfully on CPU")
        except Exception as e:
            logger.warning(f"Failed to load Whisper on GPU: {e}. Falling back to CPU.")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="float32")
            logger.info("Whisper model loaded successfully on CPU")
    return _whisper_model

def download_audio_and_transcribe(video_id):
    temp_dir = d_drive_temp
    os.makedirs(temp_dir, exist_ok=True)
    
    audio_path_tmpl = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    # yt-dlp command to download audio as m4a
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "ba[ext=m4a]/ba",
        "-x", "--audio-format", "m4a",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--quiet",
        "-o", audio_path_tmpl
    ]
    
    cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
        
    cmd.append(video_url)
    
    logger.info(f"Downloading audio for Whisper fallback: {video_id}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        audio_file = os.path.join(temp_dir, f"{video_id}.m4a")
        if not os.path.exists(audio_file):
            matches = glob.glob(os.path.join(temp_dir, f"{video_id}.*"))
            if matches:
                audio_file = matches[0]
            else:
                logger.error(f"Failed to find downloaded audio file for {video_id}")
                return None
                
        model = get_whisper_model()
        logger.info(f"Transcribing audio locally using Whisper for: {video_id}...")
        segments, info = model.transcribe(audio_file, beam_size=5, language="th")
        
        transcript = []
        for segment in segments:
            transcript.append({
                "text": segment.text.strip(),
                "start": round(segment.start, 2),
                "duration": round(segment.end - segment.start, 2)
            })
            
        try:
            os.remove(audio_file)
        except Exception:
            pass
            
        logger.info(f"-> Whisper successfully generated transcript for {video_id} ({len(transcript)} lines)")
        return transcript
        
    except Exception as e:
        logger.error(f"Local Whisper transcription failed for {video_id}: {e}")
        for f in glob.glob(os.path.join(temp_dir, f"{video_id}.*")):
            try:
                os.remove(f)
            except Exception:
                pass
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
        
        # 4. Fallback to Whisper if subtitles are unavailable on YouTube
        if not transcript:
            transcript = download_audio_and_transcribe(video_id)
        
        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                success_count += 1
                logger.info(f"-> Successfully cached transcript for {video_id} ({len(transcript)} lines)")
            except Exception as e:
                logger.error(f"-> Failed to write transcript to DB: {e}")
        else:
            logger.warning(f"-> Transcripts completely unavailable/failed for {video_id}")
            failed_count += 1
            
        # Mild pause to be polite and avoid rate limits
        import random
        time.sleep(random.uniform(2.0, 4.0))
        
    logger.info("========================================")
    logger.info("yt-dlp Transcript downloading completed!")
    logger.info(f"Total processed: {len(videos)}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Skipped (already cached): {skipped_count}")
    logger.info(f"Failed / Unavailable: {failed_count}")

if __name__ == "__main__":
    main()
