import time
import os
from faster_whisper import WhisperModel

# Set Hugging Face cache
os.environ["HF_HOME"] = "D:\\huggingface_cache"

print("Loading model...")
model = WhisperModel("tiny", device="cpu", compute_type="float32", cpu_threads=1)
print("Model loaded.")

print("Starting transcription...")
t0 = time.time()
segments, info = model.transcribe("D:/youtube_search_temp/fKNhhDb-8xs.m4a", beam_size=1, language="th")
print(f"Transcribe returned. Language: {info.language} (prob: {info.language_probability:.2f})")

segment_list = []
for idx, segment in enumerate(segments):
    segment_list.append(segment.text)
    # Print only segment index and start/end times to avoid character encoding issues
    print(f"Segment {idx}: start={segment.start:.2f}, end={segment.end:.2f}")

print(f"Completed! Total segments: {len(segment_list)}")
print(f"Time taken: {time.time() - t0:.2f} seconds")
