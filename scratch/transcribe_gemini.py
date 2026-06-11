import os
import sys
import time
import subprocess
import glob
import json
import logging
import pydantic
from typing import List
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

# Check dependencies
try:
    from google import genai
except ImportError:
    logger.error("The 'google-genai' package is not installed.")
    logger.info("Please install it using: pip install google-genai")
    sys.exit(1)

# Temp storage
if os.path.exists("D:\\"):
    d_drive_temp = "D:\\youtube_search_temp"
else:
    d_drive_temp = os.path.join(base_dir, "scratch", "temp_subs")
os.makedirs(d_drive_temp, exist_ok=True)

from backend.utils.youtube import YouTubeClient

# Pydantic Schemas for Structured Output
class TranscriptSegment(pydantic.BaseModel):
    text: str
    start: float
    duration: float

class TranscriptResponse(pydantic.BaseModel):
    segments: List[TranscriptSegment]

# Prompt that biases Gemini for Islamic religious terminology
GEMINI_TRANSCRIPT_PROMPT = (
    "คุณเป็นผู้เชี่ยวชาญการถอดความไฟล์เสียงภาษาไทย "
    "กรุณาถอดความเสียงบรรยายศาสนาอิสลามนี้อย่างละเอียด คำต่อคำ และห้ามสรุปความเด็ดขาด "
    "สิ่งสำคัญ: ต้องสะกดคำเฉพาะทางศาสนาและภาษาอาหรับให้ถูกต้องตามหลักภาษาไทยมุสลิม "
    "(เช่น อัลลอฮ์, บิสมิลลาฮ์, อัลฮัมดุลิลลาฮ์, ซิกิร, ดุอาอ์, นบี, ศอฮาบะฮ์, เตาฮีด, สะลัฟ, อิบาดะฮ์, ฟิกฮ์, มุสลิม, วะเราะห์มะตุลลอฮ์, ซุนนะฮ์, บิดอะฮ์, หะดีษ, ซูเราะฮ์, อายะฮ์) "
    "นำข้อความที่ถอดความได้แบ่งออกเป็นเซกเมนต์ย่อยๆ ตามช่วงเวลาในการพูดจริง"
)

def update_status(index, total, video_id, video_title, progress_state, success_count, fail_count, status="running"):
    status_path = os.path.join(base_dir, "backend", "cache", "transcription_status.json")
    os.makedirs(os.path.dirname(status_path), exist_ok=True)
    status_data = {
        "status": status,
        "current_index": index,
        "total_to_process": total,
        "current_video_id": video_id,
        "current_video_title": video_title,
        "progress_state": progress_state, # 'downloading', 'uploading_gemini', 'processing_gemini', 'generating_transcript', 'success', 'transcription_failed', 'download_failed', 'completed'
        "success_count": success_count,
        "fail_count": fail_count,
        "last_updated": time.time()
    }
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write status file: {e}")

def transcribe_with_gemini(audio_path, video_id, video_title="", idx=0, total=0, success_count=0, fail_count=0, retries=5, initial_backoff=10):
    """Uploads audio to Gemini File API and transcribes it with retry logic."""
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("YOUTUBE_API_KEY")
    if not gemini_key:
        logger.error("GEMINI_API_KEY or YOUTUBE_API_KEY is not set in environment or .env file.")
        return None

    # Initialize google-genai client
    client = genai.Client(api_key=gemini_key)
    
    uploaded_file = None
    try:
        logger.info(f"Uploading {audio_path} to Gemini File API...")
        update_status(idx, total, video_id, video_title, "uploading_gemini", success_count, fail_count)
        uploaded_file = client.files.upload(file=audio_path)
        logger.info(f"Uploaded successfully. File name in API: {uploaded_file.name}")
        
        # Poll for processing
        wait_start = time.time()
        while uploaded_file.state.name == "PROCESSING":
            if time.time() - wait_start > 300: # 5 min timeout
                raise TimeoutError("Gemini File API processing timed out.")
            logger.info("Waiting for Gemini API to finish processing audio file...")
            update_status(idx, total, video_id, video_title, "processing_gemini", success_count, fail_count)
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise ValueError(f"Gemini File API failed to process the file.")
            
        logger.info(f"File is ready (state: {uploaded_file.state.name}). Generating transcript...")
        update_status(idx, total, video_id, video_title, "generating_transcript", success_count, fail_count)
        
        # Generate content with exponential backoff for 503/429 errors
        for attempt in range(1, retries + 1):
            try:
                t0 = time.time()
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[uploaded_file, GEMINI_TRANSCRIPT_PROMPT],
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": TranscriptResponse
                    }
                )
                logger.info(f"Gemini transcription response received in {time.time() - t0:.1f}s")
                
                # Parse output
                raw_text = response.text.strip()
                response_data = json.loads(raw_text)
                
                # Extract and format segments list
                transcript = []
                for item in response_data.get("segments", []):
                    transcript.append({
                        "text": item.get("text", "").strip(),
                        "start": round(float(item.get("start", 0.0)), 2),
                        "duration": round(float(item.get("duration", 0.0)), 2)
                    })
                
                if not transcript:
                    logger.warning(f"Gemini returned empty transcript segments list for {video_id}")
                    
                logger.info(f"Successfully transcribed {video_id} using Gemini: {len(transcript)} segments found.")
                return transcript
                
            except Exception as api_err:
                err_msg = str(api_err)
                is_transient = "503" in err_msg or "429" in err_msg or "UNAVAILABLE" in err_msg or "ResourceExhausted" in err_msg
                
                if is_transient and attempt < retries:
                    backoff = initial_backoff * (2 ** (attempt - 1))
                    logger.warning(f"Gemini API transient error (attempt {attempt}/{retries}): {err_msg}. "
                                   f"Retrying in {backoff} seconds...")
                    time.sleep(backoff)
                else:
                    raise api_err

    except Exception as e:
        logger.error(f"Gemini transcription failed for {video_id}: {e}")
        return None
    finally:
        # Always clean up the file from Gemini cloud storage
        if uploaded_file:
            try:
                logger.info(f"Deleting remote file {uploaded_file.name} from Gemini API...")
                client.files.delete(name=uploaded_file.name)
            except Exception as clean_err:
                logger.warning(f"Failed to delete remote file from Gemini: {clean_err}")

def download_audio(video_id):
    """Downloads audio of a YouTube video as m4a format."""
    temp_dir = d_drive_temp
    audio_path_tmpl = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "ba[ext=m4a]/ba",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--quiet",
        "-o", audio_path_tmpl
    ]
    
    # Check for cookies
    cookies_path = os.path.join(base_dir, "cookies_new.txt")
    if not os.path.exists(cookies_path):
        cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
        
    cmd.append(video_url)
    
    logger.info(f"Downloading audio for video: {video_id}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        audio_file = os.path.join(temp_dir, f"{video_id}.m4a")
        if not os.path.exists(audio_file):
            matches = glob.glob(os.path.join(temp_dir, f"{video_id}.*"))
            if matches:
                audio_file = matches[0]
            else:
                logger.error(f"Downloaded audio file not found for {video_id}")
                return None
        return audio_file
    except Exception as e:
        logger.error(f"Failed to download audio via yt-dlp: {e}")
        return None

def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    client = YouTubeClient(api_key=api_key)
    
    if not client.db_manager.use_firebase:
        logger.error("Firebase is not initialized. Check your credentials in .env file.")
        sys.exit(1)
        
    db = client.db_manager.db
    channel_name = "@AssabiqoonPublisher"
    limit = 5000
    
    # Load videos
    cache_key = f"channel_videos_{channel_name}_{limit}"
    videos_doc = db.collection("channel_videos").document(cache_key).get()
    
    if not videos_doc.exists:
        logger.error("Channel videos cache not found in Firestore. Please run Phase 1 first.")
        sys.exit(1)
        
    videos = videos_doc.to_dict().get("data", [])
    logger.info(f"Loaded {len(videos)} videos from channel videos cache.")
    
    # Pre-fetch existing documents to check status
    logger.info("Fetching existing transcript states from Firestore...")
    doc_refs = [db.collection("transcripts").document(v["id"]) for v in videos]
    existing_docs = {}
    BATCH_SIZE = 500
    for batch_start in range(0, len(doc_refs), BATCH_SIZE):
        batch = doc_refs[batch_start : batch_start + BATCH_SIZE]
        for snap in db.get_all(batch):
            existing_docs[snap.id] = snap.to_dict() if snap.exists else None
            
    # Filter videos to process
    to_process = []
    skipped_count = 0
    
    # Options: --all (transcribe everything missing), default (only transcribe those marked with no_subtitle: True)
    process_all = "--all" in sys.argv
    
    for video in videos:
        vid = video["id"]
        doc_data = existing_docs.get(vid)
        
        if doc_data is not None:
            # If it's already marked as no_subtitle=True, we should transcribe it using Gemini!
            is_no_sub = isinstance(doc_data, dict) and doc_data.get("no_subtitle") is True
            if is_no_sub:
                to_process.append(video)
            else:
                skipped_count += 1
        else:
            # Not in Firestore at all
            if process_all:
                to_process.append(video)
            else:
                skipped_count += 1 # Normally we check subtitles first, so we skip if not marked yet
                
    logger.info(f"Videos to transcribe with Gemini: {len(to_process)} (Skipped: {skipped_count})")
    
    # Initialize status file
    if to_process:
        update_status(0, len(to_process), "", "", "starting", 0, 0, status="running")
    else:
        update_status(0, 0, "", "", "idle", 0, 0, status="idle")
        
    # Sequential loop to avoid exceeding Gemini API rate limits (Free Tier is 15 RPM, 1M TPM)
    # Plus, sequential download and transcription prevents disk and CPU spikes.
    delay_seconds = 6 # Add delay between requests to be safe
    success_count = 0
    fail_count = 0
    
    try:
        for idx, video in enumerate(to_process, start=1):
            vid = video["id"]
            title = video["title"]
            logger.info(f"[{idx}/{len(to_process)}] Processing: {vid} | {title[:50]}...")
            
            # Update status: Downloading
            update_status(idx, len(to_process), vid, title, "downloading", success_count, fail_count)
            
            # 1. Download audio
            audio_file = download_audio(vid)
            if not audio_file:
                logger.error(f"Skipping {vid} due to audio download failure.")
                fail_count += 1
                update_status(idx, len(to_process), vid, title, "download_failed", success_count, fail_count)
                continue
                
            # 2. Transcribe using Gemini API
            transcript = transcribe_with_gemini(
                audio_file, vid, video_title=title, idx=idx, total=len(to_process), 
                success_count=success_count, fail_count=fail_count
            )
            
            # Clean up local file immediately
            try:
                os.remove(audio_file)
            except Exception:
                pass
                
            if transcript:
                try:
                    # Save to database (replaces no_subtitle marker)
                    client.db_manager.set_document("transcripts", vid, transcript)
                    success_count += 1
                    logger.info(f"[{idx}/{len(to_process)}] ✓ Successfully saved transcript for {vid}")
                    update_status(idx, len(to_process), vid, title, "success", success_count, fail_count)
                except Exception as e:
                    logger.error(f"[{idx}/{len(to_process)}] Failed to save to Firestore: {e}")
                    fail_count += 1
                    update_status(idx, len(to_process), vid, title, "save_failed", success_count, fail_count)
            else:
                fail_count += 1
                logger.warning(f"[{idx}/{len(to_process)}] ✗ Transcription failed for {vid}")
                update_status(idx, len(to_process), vid, title, "transcription_failed", success_count, fail_count)
                
            # Rate limit spacing (Free tier: 15 RPM)
            if idx < len(to_process):
                logger.info(f"Throttling: waiting {delay_seconds} seconds to avoid API rate limits...")
                time.sleep(delay_seconds)
    except KeyboardInterrupt:
        logger.warning("Transcription loop interrupted by user.")
        update_status(0, 0, "", "", "stopped", success_count, fail_count, status="idle")
        sys.exit(0)
    except Exception as run_err:
        logger.error(f"Fatal transcription loop error: {run_err}")
        update_status(0, 0, "", "", "stopped", success_count, fail_count, status="idle")
        raise run_err
            
    logger.info("=" * 50)
    logger.info("Gemini Transcription completed!")
    logger.info(f"Total processed: {len(to_process)}")
    logger.info(f"Success: {success_count}")
    logger.info(f"Failures: {fail_count}")
    
    update_status(len(to_process), len(to_process), "", "", "completed", success_count, fail_count, status="idle")

if __name__ == "__main__":
    main()
