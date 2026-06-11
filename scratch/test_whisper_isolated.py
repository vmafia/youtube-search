import time
from faster_whisper import WhisperModel

print("Loading model...")
try:
    model = WhisperModel("base", device="cpu", compute_type="float32")
    print("Model loaded successfully")
except Exception as e:
    print("Failed to load model:", e)
    exit(1)

print("Starting transcription...")
t0 = time.time()
try:
    segments, info = model.transcribe("D:/youtube_search_temp/fKNhhDb-8xs.m4a", beam_size=5, language="th")
    print("Transcribe function returned. Info:", info)
    for idx, segment in enumerate(segments):
        print(f"Segment {idx}: {segment.text} ({segment.start:.2f} -> {segment.end:.2f})")
    print(f"Done in {time.time() - t0:.2f} seconds")
except Exception as e:
    print("Error during transcription:", e)
