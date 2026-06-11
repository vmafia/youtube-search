import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

os.environ["HF_HOME"] = "D:\\huggingface_cache"

from faster_whisper import WhisperModel

def main():
    audio_path = "D:\\youtube_search_temp\\fKNhhDb-8xs.m4a"
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found at {audio_path}")
        return

    logger.info("Initializing Whisper Model...")
    model = WhisperModel("tiny", device="cpu", compute_type="float32", cpu_threads=1)
    logger.info("Whisper Model initialized. Transcribing...")
    
    segments, info = model.transcribe(audio_path, beam_size=1, language="th")
    logger.info(f"Got segments generator. Info duration: {info.duration}")
    
    for segment in segments:
        logger.info(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
        
    logger.info("Finished transcription test!")

if __name__ == "__main__":
    main()
