import os
import re
import sys
import json
import subprocess
from dotenv import load_dotenv

# Add backend directory to path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

load_dotenv(os.path.join(base_dir, ".env"))

def sanitize_key(key: str) -> str:
    return "".join([c if c.isalnum() else "_" for c in key])

def download_audio(video_id: str, output_path: str) -> bool:
    print(f"[*] Downloading audio for video {video_id} using yt-dlp...")
    
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", output_path,
    ]
    
    # Use cookies if available
    cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
        print(f"[*] Using cookies from {cookies_path}")
        
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    
    try:
        subprocess.run(cmd, check=True)
        # yt-dlp will append .mp3 to the output template if not already present
        actual_path = output_path if output_path.endswith(".mp3") else f"{output_path}.mp3"
        if os.path.exists(actual_path):
            return True
        # Check if it saved without extra .mp3
        if os.path.exists(output_path):
            return True
        return False
    except Exception as e:
        print(f"[!] Failed to download audio: {e}")
        return False

def transcribe_with_openai(audio_path: str) -> list:
    print("[*] Transcribing audio using OpenAI Whisper API...")
    try:
        from openai import OpenAI
    except ImportError:
        print("[!] openai package is not installed. Installing it now...")
        subprocess.run([sys.executable, "-m", "pip", "install", "openai"], check=True)
        from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[!] OPENAI_API_KEY environment variable is not set in .env file.")
        return []

    client = OpenAI(api_key=api_key)
    
    # Whisper API accepts max 25MB, for larger files you might need chunking.
    # Usually YouTube audio-only is small, but if it is too big, warn the user.
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"[*] Audio file size: {file_size_mb:.2f} MB")
    
    if file_size_mb > 25:
        print("[!] File size exceeds 25MB limit. Please compress it or use local whisper.")
        return []

    with open(audio_path, "rb") as audio_file:
        transcript_response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )
    
    # Format to match YouTubeTranscriptApi output: [{"text": "...", "start": 0.0, "duration": 4.5}]
    formatted_transcript = []
    segments = getattr(transcript_response, "segments", [])
    for segment in segments:
        start = segment.get("start", 0.0)
        end = segment.get("end", 0.0)
        duration = max(0.0, end - start)
        formatted_transcript.append({
            "text": segment.get("text", "").strip(),
            "start": round(start, 2),
            "duration": round(duration, 2)
        })
        
    return formatted_transcript

def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_whisper.py <youtube_video_id>")
        sys.exit(1)
        
    video_id = sys.argv[1].strip()
    
    # Resolve full URL to ID if pasted
    if "youtube.com" in video_id or "youtu.be" in video_id:
        match = re.search(r"(?:v=|\/)([\w-]+)(?:\?|&|$)", video_id)
        if match:
            video_id = match.group(1)
        else:
            print("[!] Could not parse video ID from URL")
            sys.exit(1)

    print(f"[*] Target Video ID: {video_id}")
    
    # 1. Paths Setup
    temp_audio_path = os.path.join(base_dir, "scratch", f"temp_{video_id}")
    cache_dir = os.environ.get("CACHE_DIR", os.path.join(base_dir, "backend", "cache"))
    transcripts_dir = os.path.join(cache_dir, "transcripts")
    os.makedirs(transcripts_dir, exist_ok=True)
    
    clean_id = sanitize_key(video_id)
    final_cache_path = os.path.join(transcripts_dir, f"{clean_id}.json")
    
    # 2. Download Audio
    success = download_audio(video_id, temp_audio_path)
    if not success:
        print("[!] Audio download failed.")
        sys.exit(1)
        
    actual_audio_path = temp_audio_path if os.path.exists(temp_audio_path) else f"{temp_audio_path}.mp3"
    
    # 3. Transcribe
    try:
        transcript = transcribe_with_openai(actual_audio_path)
        if not transcript:
            print("[!] Transcription failed or returned empty results.")
            sys.exit(1)
            
        # 4. Save to cache
        with open(final_cache_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
            
        print(f"[+] Successfully transcribed and saved cache to: {final_cache_path}")
        
    finally:
        # Cleanup temp audio
        if os.path.exists(actual_audio_path):
            os.remove(actual_audio_path)
            print("[*] Cleaned up temporary audio files.")

if __name__ == "__main__":
    main()
