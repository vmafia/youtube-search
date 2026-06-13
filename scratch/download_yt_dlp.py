import os
import sys
import time
import subprocess
import glob
import re
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Setup logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Max concurrent workers for transcript fetching (Phase 1)
# Higher = faster, but risks YouTube rate-limiting. 20 is a safe sweet spot.
MAX_WORKERS = 20

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
        import requests
        if os.path.exists(cookies_path):
            import http.cookiejar
            session = requests.Session()
            cj = http.cookiejar.MozillaCookieJar(cookies_path)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
            api = YouTubeTranscriptApi(http_client=session)
        else:
            api = YouTubeTranscriptApi()
            
        fetched = api.fetch(video_id, languages=["th", "en"])
        return [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
    except Exception as e:
        logger.debug(f"YouTubeTranscriptApi failed for {video_id}: {e}")
    return None


WHISPER_ISLAMIC_PROMPT = (
    "บรรยายศาสนาอิสลามภาษาไทย คำศัพท์ที่ใช้บ่อย: "
    "อัลลอฮ์ บิสมิลลาฮ์ อัลฮัมดุลิลลาฮ์ อัสสลามุอะลัยกุม วะเราะห์มะตุลลอฮิ วะบะรอกาตุฮ์ "
    "ซิกิร ดุอาอ์ ฟิกฮ์ อิบาดะฮ์ ตักวา อีมาน อิสลาม มุสลิม มุสลิมะฮ์ "
    "ซุนนะฮ์ บิดอะฮ์ หะดีษ กุรอาน ซูเราะฮ์ อายะฮ์ ตัฟซีร "
    "ศอลาฮ์ ละหมาด ซะกาต ซิยาม ฮัจญ์ ญิฮาด "
    "นบี รอซูล ศอฮาบะฮ์ ตาบิอีน สะลัฟ "
    "อะกีดะฮ์ เตาฮีด ชิริก กุฟร์ มุนาฟิก "
    "มัสยิด มักกะฮ์ มะดีนะฮ์ กะอ์บะฮ์ "
    "อัซซาบิกูน อัสสาบิกูน อัสสะบีล "
    "รอมาดอน อีดิ้ลฟิฏร์ อีดิ้ลอัฎฮา "
    "วะลิยุลลอฮ์ อุลามาอ์ ชัยคฺ อุสตาซ"
)

def get_whisper_model():
    global _whisper_model, _whisper_beam_size
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        try:
            # Attempt CUDA loading — use large-v3 on GPU for best accuracy
            logger.info("Initializing faster-whisper model ('large-v3') on GPU...")
            _whisper_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
            _whisper_beam_size = 5
            logger.info("Whisper large-v3 loaded successfully on Nvidia CUDA GPU")
        except Exception as e:
            logger.warning(f"Failed to load Whisper on GPU: {e}. Falling back to CPU with 'large-v3' model.")
            try:
                # large-v3 on CPU with int8 quantization — slower but much better than 'small'
                _whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=6)
                _whisper_beam_size = 3
                logger.info("Whisper 'large-v3' model loaded on CPU (int8, threads=6)")
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
            initial_prompt=WHISPER_ISLAMIC_PROMPT,  # ช่วย recognize คำศัพท์อิสลาม
            vad_filter=True,       # skip silent parts → faster
            condition_on_previous_text=True   # ใช้ context ช่วยคำถัดไปให้ถูกกว่า
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
    #   (default)  Phase 1 - fast: API only, mark no-subtitle videos
    #   --whisper  Phase 2 - slow: Whisper for videos marked as no_subtitle
    use_whisper = "--whisper" in sys.argv
    if use_whisper:
        logger.info("=== PHASE 2: Whisper mode — transcribing no-subtitle videos ===")
    else:
        logger.info("=== PHASE 1: Fast mode (concurrent) — API subtitles only ===")

    # 1. Retrieve the list of channel videos from Firestore
    cache_key = f"channel_videos_{channel_name}_{limit}"
    videos_doc = db.collection("channel_videos").document(cache_key).get()

    if not videos_doc.exists:
        logger.error("Channel videos cache not found in Firestore.")
        sys.exit(1)

    videos = videos_doc.to_dict().get("data", [])
    logger.info(f"Loaded {len(videos)} videos from channel videos cache.")

    # ── 2. BATCH PRE-FETCH all transcript doc statuses ──────────────────────
    # One round-trip to Firestore instead of 3268 sequential .get() calls.
    logger.info("Pre-fetching existing transcript statuses from Firestore (batch)...")
    t0 = time.time()
    doc_refs = [db.collection("transcripts").document(v["id"]) for v in videos]

    existing_docs = {}  # video_id -> dict | None
    BATCH_SIZE = 500    # Firestore get_all has no hard limit but 500 is safe
    for batch_start in range(0, len(doc_refs), BATCH_SIZE):
        batch = doc_refs[batch_start: batch_start + BATCH_SIZE]
        for snap in db.get_all(batch):
            existing_docs[snap.id] = snap.to_dict() if snap.exists else None

    logger.info(f"Batch pre-fetch done in {time.time() - t0:.1f}s — "
                f"{sum(1 for v in existing_docs.values() if v is not None)} docs found.")

    # 3. Filter videos that actually need processing
    to_process = []
    skipped_count = 0
    for video in videos:
        vid = video["id"]
        doc_data = existing_docs.get(vid)
        if doc_data is not None:
            is_no_sub = isinstance(doc_data, dict) and doc_data.get("no_subtitle") is True
            if use_whisper and is_no_sub:
                to_process.append(video)      # Phase 2: process these
            else:
                skipped_count += 1            # Already done (or already marked), skip
        else:
            to_process.append(video)          # Not in Firestore yet

    logger.info(f"Videos to process: {len(to_process)} | Already skipped: {skipped_count}")

    # ── 4. CONCURRENT PROCESSING ─────────────────────────────────────────────
    success_count = 0
    no_sub_count = 0
    lock = threading.Lock()
    total = len(to_process)

    def process_video(idx_video):
        idx, video = idx_video
        video_id = video["id"]
        title = video["title"]
        transcript = None

        if use_whisper:
            logger.info(f"[{idx}/{total}] Whisper: {video_id} — {title[:40]}")
            transcript = download_audio_and_transcribe(video_id)
        else:
            transcript = download_subs_api(video_id)

        if transcript:
            try:
                client.db_manager.set_document("transcripts", video_id, transcript)
                with lock:
                    nonlocal success_count
                    success_count += 1
                    sc = success_count
                logger.info(f"[{idx}/{total}] ✓ ({sc} new) {video_id} ({len(transcript)} lines) — {title[:40]}")
            except Exception as e:
                logger.error(f"[{idx}/{total}] Failed to write {video_id}: {e}")
        else:
            try:
                db.collection("transcripts").document(video_id).set(
                    {"no_subtitle": True, "title": title}
                )
            except Exception as e:
                logger.warning(f"Failed to write no_subtitle marker for {video_id}: {e}")
            with lock:
                nonlocal no_sub_count
                no_sub_count += 1
                nsc = no_sub_count
            if nsc <= 5 or nsc % 100 == 0:
                logger.info(f"[{idx}/{total}] No subtitle ({nsc} total): {video_id} — {title[:40]}")

    # Phase 1 is I/O-bound → threads work great.
    # Phase 2 (Whisper) is CPU-bound → keep sequential to avoid OOM on large models.
    workers = MAX_WORKERS if not use_whisper else 1
    logger.info(f"Starting {'concurrent' if workers > 1 else 'sequential'} processing "
                f"with {workers} worker(s)...")

    indexed = list(enumerate(to_process, start=1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_video, iv): iv for iv in indexed}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                iv = futures[future]
                logger.error(f"Unhandled error for {iv[1]['id']}: {exc}")

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

