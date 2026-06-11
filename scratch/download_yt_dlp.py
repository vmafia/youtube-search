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
        "--socket-timeout", "15",
        "--quiet",
        "-o", output_tmpl
    ]
    
    # Use cookies if available to bypass 429 blocks
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
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

def download_subs_api(video_id):
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
        cookies_path = os.path.join(base_dir, "cookies.txt")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        if os.path.exists(cookies_path):
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"], cookies=cookies_path)
        else:
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=["th", "en"])
        return [{"text": s["text"], "start": s["start"], "duration": s["duration"]} for s in fetched]
    except Exception as e:
        logger.debug(f"YouTubeTranscriptApi failed for {video_id}: {e}")
    return None


# Global whisper model cache
_whisper_model = None
_whisper_beam_size = 5

def get_whisper_model():
    global _whisper_model, _whisper_beam_size
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        try:
            # Attempt CUDA loading
            logger.info("Initializing faster-whisper model ('base') on GPU...")
            _whisper_model = WhisperModel("base", device="cuda", compute_type="float16")
            _whisper_beam_size = 5
            logger.info("Whisper model loaded successfully on Nvidia CUDA GPU")
        except Exception as e:
            logger.warning(f"Failed to load Whisper on GPU: {e}. Falling back to CPU with 'small' model.")
            try:
                # Use small model on CPU with more threads for better accuracy on Thai
                _whisper_model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
                _whisper_beam_size = 3
                logger.info("Whisper 'small' model loaded successfully on CPU (threads=4, int8)")
            except Exception as cpu_err:
                logger.error(f"Failed to load Whisper on CPU as well: {cpu_err}")
                raise cpu_err
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
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--quiet",
        "-o", audio_path_tmpl
    ]
    
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
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
        segments, info = model.transcribe(
            audio_file,
            beam_size=_whisper_beam_size,
            language="th",
            vad_filter=True,       # skip silent parts → faster
            condition_on_previous_text=False  # avoid hallucination loop
        )
        logger.info(f"Processing audio with duration {info.duration:.1f}s | detected lang: {info.language} ({info.language_probability:.0%})")
        
        transcript = []
        for segment in segments:
            text = segment.text.strip()
            if text:  # skip empty segments
                transcript.append({
                    "text": text,
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
    
    # Modes:
    #   (default)  Phase 1 - fast: API + yt-dlp only, mark no-subtitle videos
    #   --whisper  Phase 2 - slow: Whisper for videos marked as no_subtitle
    use_whisper = "--whisper" in sys.argv
    if use_whisper:
        logger.info("=== PHASE 2: Whisper mode — transcribing no-subtitle videos ===")
    else:
        logger.info("=== PHASE 1: Fast mode — API + yt-dlp subtitles only ===")
    
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
    no_sub_count = 0
    
    for i, video in enumerate(videos):
        video_id = video["id"]
        title = video["title"]
        
        # Check Firestore for existing transcript or no_subtitle marker
        try:
            doc_ref = db.collection("transcripts").document(video_id).get()
            if doc_ref.exists:
                doc_data = doc_ref.to_dict()
                is_no_sub_marker = isinstance(doc_data, dict) and doc_data.get("no_subtitle") is True
                
                if use_whisper and is_no_sub_marker:
                    # Phase 2: this is a marked no-subtitle video, process with Whisper
                    pass
                elif not use_whisper and is_no_sub_marker:
                    # Phase 1: already marked as no-subtitle, skip
                    skipped_count += 1
                    continue
                else:
                    # Has real transcript, skip
                    skipped_count += 1
                    if skipped_count % 200 == 0:
                        logger.info(f"[{i+1}/{len(videos)}] Progress: {success_count} new, {skipped_count} skipped, {no_sub_count} no-sub")
                    continue
        except Exception as e:
            logger.warning(f"Error checking Firestore for {video_id}: {e}")
        
        transcript = None
        
        if use_whisper:
            # Phase 2: Whisper transcription (download audio + transcribe)
            logger.info(f"[{i+1}/{len(videos)}] Whisper transcribing: {video_id} — {title[:35]}")
            transcript = download_audio_and_transcribe(video_id)
        else:
            # Phase 1: API only — fastest possible (~0.5s per video)
            # Skip yt-dlp here (needs EJS solve = ~8s per video = 7+ hours for 3268 videos)
            # yt-dlp is used in Phase 2 only, where we download audio anyway
            transcript = download_subs_api(video_id)
        
        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                success_count += 1
                logger.info(f"[{i+1}/{len(videos)}] ✓ Cached {video_id} ({len(transcript)} lines) — {title[:35]}")
            except Exception as e:
                logger.error(f"-> Failed to write to DB for {video_id}: {e}")
        else:
            no_sub_count += 1
            if not use_whisper:
                # Mark as no_subtitle so Phase 2 Whisper knows to process it
                try:
                    db.collection("transcripts").document(video_id).set({"no_subtitle": True, "title": title})
                except Exception as e:
                    logger.warning(f"Failed to write no_subtitle marker for {video_id}: {e}")
            if no_sub_count % 100 == 0 or no_sub_count <= 3:
                logger.info(f"[{i+1}/{len(videos)}] No subtitle ({no_sub_count} total): {video_id} — {title[:35]}")
        
        # Short pause between requests
        time.sleep(0.5)
        
    logger.info("=" * 50)
    logger.info(f"Phase {'2 (Whisper)' if use_whisper else '1 (Fast)'} completed!")
    logger.info(f"Total videos in channel: {len(videos)}")
    logger.info(f"Successfully transcribed: {success_count}")
    logger.info(f"Skipped (already done): {skipped_count}")
    if use_whisper:
        logger.info(f"Whisper failed: {no_sub_count}")
    else:
        logger.info(f"Marked for Whisper (Phase 2): {no_sub_count}")
        logger.info(f"Run with --whisper flag to process remaining {no_sub_count} videos")

if __name__ == "__main__":
    main()
