import os
import sys
import io
import time
import json
import subprocess
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.theme import Theme
from rich.table import Table

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

sys.path.append(os.path.dirname(__file__))
from backend.utils.db import DatabaseManager
from backend.config import Config

CACHE_DIR = Config.CACHE_DIR
STATUS_FILE = os.path.join(CACHE_DIR, "transcription_status.json")

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "groq": "bold magenta",
    "gemini": "bold blue",
})
console = Console(theme=custom_theme)

# ══════════════════════════════════════════════════════════════
#  Helper Functions
# ══════════════════════════════════════════════════════════════

def update_status_file(status_data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False)
    except:
        pass

import imageio_ffmpeg

def compress_for_groq(audio_path, temp_dir):
    """Compress audio to fit under Groq's 25MB limit using embedded ffmpeg."""
    import re
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb <= 24:
        return audio_path  # Already small enough

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    # Dynamically calculate bitrate based on exact duration to target < 24MB
    dur_proc = subprocess.run([ffmpeg_exe, "-i", audio_path], capture_output=True, text=True)
    dur_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", dur_proc.stderr)
    
    target_bitrate = "16k"
    if dur_match:
        hrs, mins, secs = float(dur_match.group(1)), float(dur_match.group(2)), float(dur_match.group(3))
        total_seconds = hrs * 3600 + mins * 60 + secs
        if total_seconds > 0:
            # Target 23MB = 23 * 1024 * 1024 * 8 bits
            bps = int((23 * 1024 * 1024 * 8) / total_seconds)
            bps = max(16000, min(64000, bps))  # cap at 64k, floor at 16k for acceptable quality
            target_bitrate = f"{bps // 1000}k"

    vid_name = os.path.splitext(os.path.basename(audio_path))[0]
    compressed_path = os.path.join(temp_dir, f"{vid_name}_compressed.m4a")

    result = subprocess.run(
        [ffmpeg_exe, "-y", "-i", audio_path,
         "-ac", "1", "-ar", "16000",
         "-b:a", target_bitrate,
         "-vn", compressed_path],
        capture_output=True, text=True, timeout=900
    )

    if result.returncode != 0:
        raise Exception(f"ffmpeg compression failed: {result.stderr[:200]}")

    new_size = os.path.getsize(compressed_path) / (1024 * 1024)
    console.print(f"  [dim]📦 Compressed {file_size_mb:.1f}MB → {new_size:.1f}MB ({target_bitrate}bps mono 16kHz)[/dim]")

    return compressed_path

# ══════════════════════════════════════════════════════════════
#  🚀 Groq Whisper (Primary Engine)
# ══════════════════════════════════════════════════════════════

def transcribe_with_groq_direct(send_path, groq_api_key, progress=None, task_id=None):
    """Core function to send a single audio file to Groq Whisper."""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {groq_api_key}"}

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with open(send_path, "rb") as f:
                files = {"file": (os.path.basename(send_path), f)}
                data = {
                    "model": "whisper-large-v3-turbo",
                    "response_format": "verbose_json",
                    "language": "th",
                }
                response = requests.post(url, headers=headers, files=files, data=data, timeout=300)

            if response.status_code == 200:
                break
            elif response.status_code == 429:
                wait = 30 * (attempt + 1)
                console.print(f"[warning]⏳ Groq rate limit. Waiting {wait}s (retry {attempt+1}/{max_retries})...[/warning]")
                time.sleep(wait)
            else:
                error_msg = response.json().get("error", {}).get("message", response.text[:300])
                raise Exception(f"Groq {response.status_code}: {error_msg}")
        except requests.exceptions.Timeout:
            console.print(f"[warning]⏳ Groq timeout. Retrying {attempt+1}/{max_retries}...[/warning]")
            time.sleep(10)
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(5)
    else:
        raise Exception("Groq max retries reached")

    result = response.json()
    segments = result.get("segments", [])

    transcript = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if text:
            transcript.append({
                "text": text,
                "start": round(seg["start"], 2),
                "duration": round(seg["end"] - seg["start"], 2),
                "speaker": None
            })
    return transcript

def transcribe_with_groq(audio_path, groq_api_key, temp_dir, progress=None, task_id=None):
    """Primary: Transcribe using Groq Whisper, auto-chunking large files to bypass timeouts & limits."""
    import re
    import glob

    # First, compress the audio to a standard low bitrate so it is easy to handle
    send_path = compress_for_groq(audio_path, temp_dir)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    dur_proc = subprocess.run([ffmpeg_exe, "-i", send_path], capture_output=True, text=True)
    dur_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", dur_proc.stderr)

    total_seconds = 0
    if dur_match:
        hrs, mins, secs = float(dur_match.group(1)), float(dur_match.group(2)), float(dur_match.group(3))
        total_seconds = hrs * 3600 + mins * 60 + secs

    # If the audio is short (e.g. less than 30 minutes), transcribe directly
    if total_seconds < 1800:
        if progress and task_id:
            progress.update(task_id, description="[groq]🚀 Groq Whisper: Transcribing...[/groq]")
        try:
            transcript = transcribe_with_groq_direct(send_path, groq_api_key, progress, task_id)
            if progress and task_id:
                progress.update(task_id, completed=100,
                                 description=f"[success]✅ Groq Whisper Done ({len(transcript)} segments)[/success]")
            # Cleanup
            if send_path != audio_path and os.path.exists(send_path):
                try: os.remove(send_path)
                except: pass
            return transcript
        except Exception as e:
            if send_path != audio_path and os.path.exists(send_path):
                try: os.remove(send_path)
                except: pass
            raise e

    # Otherwise, split into 20-minute (1200 seconds) chunks
    chunk_time = 1200
    vid_name = os.path.splitext(os.path.basename(audio_path))[0]
    chunk_pattern = os.path.join(temp_dir, f"chunk_{vid_name}_%03d.m4a")

    # Clean up old chunks
    for old_chunk in glob.glob(os.path.join(temp_dir, f"chunk_{vid_name}_*.m4a")):
        try: os.remove(old_chunk)
        except: pass

    if progress and task_id:
        progress.update(task_id, description="[groq]✂️ Groq Whisper: Splitting into chunks...[/groq]")

    # Split using ffmpeg segment muxer
    split_proc = subprocess.run([
        ffmpeg_exe, "-y", "-i", send_path,
        "-f", "segment", "-segment_time", str(chunk_time),
        "-c", "copy", chunk_pattern
    ], capture_output=True, text=True)

    if split_proc.returncode != 0:
        if send_path != audio_path and os.path.exists(send_path):
            try: os.remove(send_path)
            except: pass
        raise Exception(f"Failed to split audio: {split_proc.stderr[:200]}")

    chunks = sorted(glob.glob(os.path.join(temp_dir, f"chunk_{vid_name}_*.m4a")))
    if not chunks:
        if send_path != audio_path and os.path.exists(send_path):
            try: os.remove(send_path)
            except: pass
        raise Exception("No audio chunks generated")

    merged_transcript = []
    try:
        for idx, chunk_path in enumerate(chunks):
            if progress and task_id:
                progress.update(task_id, description=f"[groq]🚀 Groq: Chunk {idx+1}/{len(chunks)}...[/groq]")
            
            chunk_transcript = transcribe_with_groq_direct(chunk_path, groq_api_key, progress, task_id)
            
            # Shift timestamps of segments in this chunk
            offset = idx * chunk_time
            for seg in chunk_transcript:
                seg["start"] = round(seg["start"] + offset, 2)
                merged_transcript.append(seg)
                
            # Clean up chunk file
            try: os.remove(chunk_path)
            except: pass
    finally:
        # Final cleanup of remaining chunk files in case of errors
        for chunk_path in chunks:
            if os.path.exists(chunk_path):
                try: os.remove(chunk_path)
                except: pass
        if send_path != audio_path and os.path.exists(send_path):
            try: os.remove(send_path)
            except: pass

    if progress and task_id:
        progress.update(task_id, completed=100,
                         description=f"[success]✅ Groq Whisper Done ({len(merged_transcript)} segments via {len(chunks)} chunks)[/success]")

    return merged_transcript

# ══════════════════════════════════════════════════════════════
#  🤖 Gemini 2.0 Flash (Fallback Engine)
# ══════════════════════════════════════════════════════════════

def transcribe_with_gemini(audio_path, client, progress=None, task_id=None):
    """Fallback: Transcribe using Gemini 2.0 Flash."""
    if not client:
        raise Exception("Gemini client not available")

    if progress and task_id:
        progress.update(task_id, description="[gemini]☁️ Gemini: Uploading audio...[/gemini]")

    myfile = client.files.upload(file=audio_path)

    prompt = """
    You are an expert transcriptionist. Please transcribe the following Thai speech accurately.
    Return the transcription as a JSON array of objects. 
    Each object MUST have:
    - "text": The spoken text (in Thai).
    - "start": The start time in seconds (float).
    - "duration": The duration of the text segment in seconds (float).
    - "speaker": The name or identity of the speaker, or null.
    IMPORTANT: Output ONLY the raw JSON array. Do not use markdown code blocks.
    """

    if progress and task_id:
        progress.update(task_id, description="[gemini]🤖 Gemini: Transcribing...[/gemini]")

    max_retries = 10
    full_text = ""
    for attempt in range(max_retries):
        try:
            response_stream = client.models.generate_content_stream(
                model='gemini-2.0-flash',
                contents=[myfile, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )

            full_text = ""
            chunks = 0
            for chunk in response_stream:
                if chunk.text:
                    full_text += chunk.text
                    chunks += 1
                    if progress and task_id:
                        progress.update(task_id,
                                        description=f"[gemini]🤖 Gemini: Receiving... ({chunks} chunks)[/gemini]")
            break  # Success
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "rate" in error_str or "exhausted" in error_str:
                wait_time = 60 if attempt < 3 else 300
                console.print(f"[warning]⏳ Gemini rate limit. Waiting {wait_time}s (retry {attempt+1}/{max_retries})...[/warning]")
                time.sleep(wait_time)
            else:
                try:
                    client.files.delete(name=myfile.name)
                except:
                    pass
                raise
    else:
        try:
            client.files.delete(name=myfile.name)
        except:
            pass
        raise Exception("Gemini max retries reached")

    # Cleanup uploaded file
    try:
        client.files.delete(name=myfile.name)
    except:
        pass

    # Parse JSON
    text = full_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    transcript = json.loads(text.strip())

    if progress and task_id:
        progress.update(task_id, completed=100,
                        description=f"[success]✅ Gemini Done ({len(transcript)} segments)[/success]")

    return transcript

# ══════════════════════════════════════════════════════════════
#  Video List
# ══════════════════════════════════════════════════════════════

def get_missing_videos(channel_name: str) -> list:
    from backend.utils.youtube import YouTubeClient
    youtube_client = YouTubeClient(api_key=Config.YOUTUBE_API_KEY)
    videos = youtube_client.fetch_channel_videos(channel_name, limit=5000)

    from backend.utils.search_db import get_db_stats
    stats = get_db_stats()
    transcribed_ids_raw = stats.get("transcribed_ids")
    # Safety: if DB returned None (error), abort to prevent re-processing everything
    if transcribed_ids_raw is None:
        console.print(f"[error]❌ Database error: {stats.get('error', 'unknown')}. Aborting to prevent duplicate processing.[/error]")
        sys.exit(1)
    transcribed_ids = set(transcribed_ids_raw)

    return [v for v in videos if v["id"] not in transcribed_ids]

# ══════════════════════════════════════════════════════════════
#  🎬 Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="@AssabiqoonPublisher")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    groq_api_key = os.environ.get("GROQ_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

    gemini_client = None
    if gemini_api_key and genai:
        try:
            gemini_client = genai.Client(api_key=gemini_api_key)
        except:
            pass

    if not groq_api_key and not gemini_client:
        console.print("[error]❌ No AI API keys found! Set GROQ_API_KEY or GEMINI_API_KEY in .env[/error]")
        sys.exit(1)

    db_manager = DatabaseManager(Config.CACHE_DIR)

    # ── Header ──
    console.print(Panel.fit(
        "[bold cyan]🚀 Assabiqoon AI Transcription (Terminal)[/bold cyan]\n"
        "[dim]────────────────────────────────────────────────[/dim]\n"
        f" 🥇 [bold green]Primary:[/bold green]  {'Groq Whisper large-v3-turbo 🟢' if groq_api_key else '❌ Not configured'}\n"
        f"      🥈 [bold blue]Fallback:[/bold blue] {'Gemini 2.0 Flash 🔵' if gemini_client else '❌ Not configured'}\n"
        "[dim]────────────────────────────────────────────────[/dim]\n"
        "🎨 [bold yellow]ดูความคืบหน้าแบบการ์ตูนสดใสได้ที่:[/bold yellow] [bold underline white]http://localhost:5173[/bold underline white] ✨",
        title="🤖 AI Engines",
        border_style="blue"
    ))

    # ── Fetch videos ──
    with console.status("[cyan]📡 Fetching video list from YouTube...[/cyan]"):
        missing_videos = get_missing_videos(args.channel)
        if args.limit > 0:
            missing_videos = missing_videos[:args.limit]

    total = len(missing_videos)
    if total == 0:
        console.print("[success]🎉 No missing videos! All caught up![/success]")
        return

    console.print(f"\n[success]📋 Found {total} videos to transcribe![/success]\n")

    temp_audio_dir = os.path.join(Config.CACHE_DIR, "temp_audio")
    os.makedirs(temp_audio_dir, exist_ok=True)

    success_count = 0
    failed_count = 0
    groq_count = 0
    gemini_count = 0
    start_time = time.time()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green", finished_style="bold green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    )

    with progress:
        main_task = progress.add_task("[bold cyan]🎬 Overall Progress[/bold cyan]", total=total)

        for i, video in enumerate(missing_videos, 1):
            vid = video["id"]
            title = video["title"]
            audio_path = os.path.join(temp_audio_dir, f"{vid}.m4a")

            console.print(Panel(
                f"[bold yellow]📺 Processing {i}/{total}:[/bold yellow] {title}\n"
                f"[dim]ID: {vid}  |  ✅ {success_count}  ❌ {failed_count}  |  "
                f"Groq: {groq_count}  Gemini: {gemini_count}[/dim]",
                border_style="yellow"
            ))

            # ── Step 1: Download Audio ──
            dl_task = progress.add_task("[cyan]📥 Downloading Audio...[/cyan]", total=100)

            def hook(d):
                if d['status'] == 'downloading':
                    import re
                    p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                    p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str)
                    try:
                        progress.update(dl_task, completed=float(p_str))
                    except:
                        pass

            # Search for available cookies file
            cookies_file = None
            for name in ['cookies_new.txt', 'cookies.txt', 'youtube_cookies.txt']:
                path_cwd = os.path.join(os.getcwd(), name)
                path_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
                if os.path.exists(path_cwd):
                    cookies_file = path_cwd
                    break
                elif os.path.exists(path_script):
                    cookies_file = path_script
                    break

            # Choose best audio format (webm typically works even when m4a gets 403)
            ydl_opts = {
                'format': 'bestaudio',
                'outtmpl': audio_path.replace('.m4a', '.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [hook],
            }
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file

            # Check for existing audio file in different formats
            actual_audio_path = None
            for ext in ['.m4a', '.webm', '.ogg', '.opus', '.mp3']:
                test_path = os.path.join(temp_audio_dir, f"{vid}{ext}")
                if os.path.exists(test_path) and os.path.getsize(test_path) > 100 * 1024:
                    actual_audio_path = test_path
                    break

            dl_ok = False
            if actual_audio_path:
                file_mb = os.path.getsize(actual_audio_path) / (1024 * 1024)
                progress.update(dl_task, completed=100, description="[green]✅ Audio Cached[/green]")
                console.print(f"  [dim]📁 Cached file: {file_mb:.1f} MB ({os.path.basename(actual_audio_path)})[/dim]")
                dl_ok = True
                audio_path = actual_audio_path
            else:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([f"https://www.youtube.com/watch?v={vid}"])
                    
                    # Find which file format was actually downloaded
                    for ext in ['.m4a', '.webm', '.ogg', '.opus', '.mp3']:
                        test_path = os.path.join(temp_audio_dir, f"{vid}{ext}")
                        if os.path.exists(test_path):
                            actual_audio_path = test_path
                            break
                    
                    if actual_audio_path:
                        progress.update(dl_task, completed=100, description="[green]✅ Audio Downloaded[/green]")
                        file_mb = os.path.getsize(actual_audio_path) / (1024 * 1024)
                        console.print(f"  [dim]📁 File size: {file_mb:.1f} MB ({os.path.basename(actual_audio_path)})[/dim]")
                        dl_ok = True
                        audio_path = actual_audio_path
                    else:
                        raise FileNotFoundError("Could not locate downloaded audio file with expected extension.")
                except Exception as e:
                    console.print(f"[error]❌ Download failed: {e}[/error]")
                    progress.update(dl_task, description="[red]❌ Download Failed[/red]")


            if not dl_ok:
                failed_count += 1
                progress.update(main_task, advance=1)
                try:
                    progress.remove_task(dl_task)
                except:
                    pass
                continue

            # ── Step 2: Transcribe (Groq → Gemini fallback) ──
            ai_task = progress.add_task("[groq]🚀 AI Transcribing...[/groq]", total=None)
            transcript = None
            used_engine = None

            # Try 1: Groq Whisper (fast, no daily limit)
            if groq_api_key:
                try:
                    t0 = time.time()
                    transcript = transcribe_with_groq(audio_path, groq_api_key, temp_audio_dir, progress, ai_task)
                    elapsed = time.time() - t0
                    used_engine = "Groq"
                    groq_count += 1
                    console.print(f"  [groq]⚡ Groq Whisper took {elapsed:.1f}s[/groq]")
                except Exception as e:
                    console.print(f"[warning]⚠️ Groq failed: {e}[/warning]")
                    console.print("[info]↪ Switching to Gemini fallback...[/info]")

            # Try 2: Gemini (fallback)
            if not transcript and gemini_client:
                try:
                    progress.update(ai_task, description="[gemini]🤖 Gemini fallback...[/gemini]")
                    t0 = time.time()
                    transcript = transcribe_with_gemini(audio_path, gemini_client, progress, ai_task)
                    elapsed = time.time() - t0
                    used_engine = "Gemini"
                    gemini_count += 1
                    console.print(f"  [gemini]🤖 Gemini took {elapsed:.1f}s[/gemini]")
                except Exception as e:
                    console.print(f"[error]❌ Gemini also failed: {e}[/error]")

            if not transcript:
                console.print(f"[error]❌ All AI engines failed for {vid}[/error]\n")
                failed_count += 1
                progress.update(main_task, advance=1)
                try:
                    progress.remove_task(dl_task)
                    progress.remove_task(ai_task)
                except:
                    pass
                # Cleanup audio
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except:
                        pass
                continue

            # ── Step 3: Save to Database ──
            save_task = progress.add_task("[blue]💾 Saving to Database...[/blue]", total=None)
            try:
                db_manager.set_document("transcripts", vid, transcript)
                from backend.utils.youtube import save_transcript_to_sqlite
                save_transcript_to_sqlite(vid, transcript)
                progress.update(save_task, completed=100, description="[green]✅ Saved to Database[/green]")

                success_count += 1
                console.print(f"[success]🎉 {vid} done via {used_engine}! ({len(transcript)} segments)[/success]\n")
            except Exception as e:
                console.print(f"[error]❌ Save failed: {e}[/error]\n")
                failed_count += 1

            # ── Cleanup ──
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass

            progress.update(main_task, advance=1)
            try:
                progress.remove_task(dl_task)
                progress.remove_task(ai_task)
                progress.remove_task(save_task)
            except:
                pass

            # Brief pause between videos (respect API)
            time.sleep(2)

    # ══════════════════════════════════════════════════════════
    #  📊 Final Summary
    # ══════════════════════════════════════════════════════════
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    summary = Table(title="📊 Transcription Summary", show_header=True, header_style="bold cyan", border_style="cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right", style="bold green")
    summary.add_row("✅ Success", str(success_count))
    summary.add_row("❌ Failed", str(failed_count))
    summary.add_row("🚀 Via Groq Whisper", str(groq_count))
    summary.add_row("🤖 Via Gemini", str(gemini_count))
    summary.add_row("⏱️ Total Time", f"{minutes}m {seconds}s")
    console.print(summary)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warning]🛑 Process stopped by user.[/warning]")
