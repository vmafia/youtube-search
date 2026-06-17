import os
import sys
import io
import time
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.theme import Theme

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ Please install google-genai: pip install google-genai")
    sys.exit(1)

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
})
console = Console(theme=custom_theme)

def update_status_file(status_data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False)
    except:
        pass

def get_missing_videos(channel_name: str) -> list:
    from backend.utils.youtube import YouTubeClient
    youtube_client = YouTubeClient(api_key=Config.YOUTUBE_API_KEY)
    videos = youtube_client.fetch_channel_videos(channel_name, limit=5000)
    
    from backend.utils.search_db import get_db_stats
    stats = get_db_stats()
    transcribed_ids = set(stats.get("transcribed_ids", []))
    
    return [v for v in videos if v["id"] not in transcribed_ids]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="@AssabiqoonPublisher")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[error]GEMINI_API_KEY not found in .env[/error]")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    db_manager = DatabaseManager(Config.CACHE_DIR)
    
    console.print(Panel.fit("[bold cyan]🚀 Assabiqoon AI Transcription Dashboard 🤖[/bold cyan]", border_style="cyan"))
    
    with console.status("[cyan]Fetching video list from YouTube...[/cyan]"):
        missing_videos = get_missing_videos(args.channel)
        if args.limit > 0:
            missing_videos = missing_videos[:args.limit]

    total = len(missing_videos)
    if total == 0:
        console.print("[success]🎉 No missing videos found! All caught up![/success]")
        return

    console.print(f"[success]Found {total} videos to transcribe![/success]\n")
    
    temp_audio_dir = os.path.join(Config.CACHE_DIR, "temp_audio")
    os.makedirs(temp_audio_dir, exist_ok=True)

    success = 0
    failed = 0
    
    status_data = {
        "status": "running", "current_index": 0, "total_to_process": total,
        "success_count": 0, "fail_count": 0
    }

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
            
            # Print beautiful panel for current video
            console.print(Panel(f"[bold yellow]📺 Processing {i}/{total}:[/bold yellow] {title}\n[dim]ID: {vid}[/dim]", border_style="yellow"))
            
            # Sub-tasks
            dl_task = progress.add_task("[cyan]📥 Downloading Audio...[/cyan]", total=100)
            
            # Download with yt-dlp
            def hook(d):
                if d['status'] == 'downloading':
                    p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                    import re
                    p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str)
                    try:
                        progress.update(dl_task, completed=float(p_str))
                    except: pass

            ydl_opts = {
                'format': 'm4a/bestaudio/best',
                'outtmpl': audio_path,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [hook],
            }
            
            dl_success = False
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={vid}"])
                progress.update(dl_task, completed=100, description="[green]✅ Audio Downloaded[/green]")
                dl_success = True
            except Exception as e:
                console.print(f"[error]Failed to download {vid}: {e}[/error]")
                progress.update(dl_task, description="[red]❌ Download Failed[/red]")
                
            if not dl_success:
                failed += 1
                progress.update(main_task, advance=1)
                continue

            # Upload to Gemini
            upload_task = progress.add_task("[magenta]☁️ Uploading to AI...[/magenta]", total=None)
            try:
                myfile = client.files.upload(file=audio_path)
                progress.update(upload_task, completed=100, description="[green]✅ Uploaded to AI[/green]")
            except Exception as e:
                console.print(f"[error]Failed to upload to Gemini: {e}[/error]")
                failed += 1
                progress.update(main_task, advance=1)
                continue

            # Transcribe
            ai_task = progress.add_task("[bold magenta]🤖 AI is Transcribing (Thinking...)[/bold magenta]", total=None)
            
            prompt = """
            You are an expert transcriptionist. Please transcribe the following Thai speech accurately, segmenting by speaker shifts.
            Return the transcription as a JSON array of objects. 
            Each object MUST have:
            - "text": The spoken text (in Thai).
            - "start": The start time in seconds (float).
            - "duration": The duration of the text segment in seconds (float).
            - "speaker": The name or identity of the speaker, or null.
            IMPORTANT: Output ONLY the raw JSON array. Do not use markdown code blocks like ```json.
            """
            
            try:
                response_stream = client.models.generate_content_stream(
                    model='gemini-2.5-flash',
                    contents=[myfile, prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
                )
                
                full_text = ""
                chunks = 0
                for chunk in response_stream:
                    if chunk.text:
                        full_text += chunk.text
                        chunks += 1
                        progress.update(ai_task, description=f"[bold magenta]🤖 AI is Transcribing... (Received {chunks} chunks)[/bold magenta]")
                
                progress.update(ai_task, completed=100, description="[green]✅ AI Transcription Complete[/green]")
                
                # Parse JSON
                text = full_text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.endswith("```"): text = text[:-3]
                transcript = json.loads(text.strip())
                
                # Save
                save_task = progress.add_task("[blue]💾 Saving to Database...[/blue]", total=None)
                db_manager.set_document("transcripts", vid, transcript)
                from backend.utils.youtube import save_transcript_to_sqlite
                save_transcript_to_sqlite(vid, transcript)
                progress.update(save_task, completed=100, description="[green]✅ Saved to Database[/green]")
                
                success += 1
                console.print(f"[success]🎉 Video {vid} completed successfully![/success]\n")
                
            except Exception as e:
                console.print(f"[error]❌ AI Transcription Failed: {e}[/error]\n")
                failed += 1
                
            # Cleanup
            try:
                client.files.delete(name=myfile.name)
            except: pass
            if os.path.exists(audio_path): 
                try: os.remove(audio_path)
                except: pass
            
            # Advance main task
            progress.update(main_task, advance=1)
            
            # Remove completed subtasks to keep console clean
            progress.remove_task(dl_task)
            progress.remove_task(upload_task)
            progress.remove_task(ai_task)
            if 'save_task' in locals(): progress.remove_task(save_task)
            
            # Short sleep
            time.sleep(2)
            
    console.print(Panel(f"[bold green]🏁 Process Completed![/bold green]\nSuccess: {success}\nFailed: {failed}", border_style="green"))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warning]🛑 Process stopped by user.[/warning]")
