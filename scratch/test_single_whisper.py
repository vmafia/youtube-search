import os
import sys
import logging
import subprocess
import glob
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

os.environ["HF_HOME"] = "D:\\huggingface_cache"

from faster_whisper import WhisperModel

def main():
    video_id = "fKNhhDb-8xs"
    temp_dir = "D:\\youtube_search_temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    audio_path_tmpl = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "ba[ext=m4a]/ba",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-o", audio_path_tmpl,
        video_url
    ]
    
    logger.info(f"Downloading audio for {video_id}...")
    subprocess.run(cmd, check=True)
    
    audio_file = os.path.join(temp_dir, f"{video_id}.m4a")
    if not os.path.exists(audio_file):
        matches = glob.glob(os.path.join(temp_dir, f"{video_id}.*"))
        if matches:
            audio_file = matches[0]
        else:
            logger.error("Audio file not found!")
            return
            
    logger.info(f"Audio file is at: {audio_file}, size: {os.path.getsize(audio_file)} bytes")
    
    logger.info("Loading tiny whisper model on CPU...")
    model = WhisperModel("tiny", device="cpu", compute_type="float32", cpu_threads=1)
    
    logger.info("Transcribing...")
    segments, info = model.transcribe(audio_file, beam_size=1, language="th")
    logger.info(f"Detected language: {info.language} with probability {info.language_probability:.2f}")
    
    segments = list(segments)
    logger.info(f"Number of segments: {len(segments)}")
    for s in segments:
        print(f"[{s.start:.2f}s -> {s.end:.2f}s] {s.text}")

if __name__ == "__main__":
    main()
