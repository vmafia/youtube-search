import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

os.environ["HF_HOME"] = "D:\\huggingface_cache"

from faster_whisper import WhisperModel

def main():
    audio_file = "D:\\youtube_search_temp\\fKNhhDb-8xs.m4a"
    if not os.path.exists(audio_file):
        logger.error(f"Audio file not found at {audio_file}")
        return
        
    logger.info("Loading model...")
    model = WhisperModel("tiny", device="cpu", compute_type="float32", cpu_threads=1)
    
    # Try 1: auto-detect language
    logger.info("Test 1: auto-detect language, beam_size=1")
    segments, info = model.transcribe(audio_file, beam_size=1)
    logger.info(f"Detected language: {info.language} with prob {info.language_probability:.2f}")
    segments_list = list(segments)
    logger.info(f"Segments count: {len(segments_list)}")
    for s in segments_list:
        print(f"  [{s.start:.2f}s -> {s.end:.2f}s] {s.text}")
        
    # Try 2: beam_size=5, language="th"
    logger.info("Test 2: language='th', beam_size=5")
    segments, info = model.transcribe(audio_file, beam_size=5, language="th")
    segments_list = list(segments)
    logger.info(f"Segments count: {len(segments_list)}")
    for s in segments_list:
        print(f"  [{s.start:.2f}s -> {s.end:.2f}s] {s.text}")

if __name__ == "__main__":
    main()
