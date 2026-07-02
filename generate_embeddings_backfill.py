import argparse
import json
import os
import sys
import time
from pathlib import Path

import libsql_client
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

# Force UTF-8 safely for Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from backend.config import Config
from backend.utils.search_db import ensure_tables, get_db_client
from backend.utils.youtube import generate_embeddings_voyage

load_dotenv()
console = Console(force_terminal=True, force_interactive=True)

CHECKPOINT_PATH = Path("backend/cache/embedding_backfill_checkpoint.json")


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_checkpoint(data: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_video_ids(client, limit: int) -> list[str]:
    # Fetch all from helper table (very fast) and we will filter in Python
    rs = client.execute("SELECT video_id FROM transcribed_videos")
    return [row[0] for row in rs.rows]


def fetch_transcript_rows(client, video_id: str) -> list[dict]:
    rs = client.execute(
        """
        SELECT start_time, text
        FROM transcripts
        WHERE video_id = ?
        ORDER BY start_time ASC
        """,
        [video_id],
    )
    return [{"start": row[0], "text": row[1]} for row in rs.rows]


def save_embeddings(client, video_id: str, rows: list[dict], embeddings: list[list[float]], batch_size: int) -> None:
    statements = [libsql_client.Statement("DELETE FROM transcript_embeddings WHERE video_id = ?", [video_id])]

    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        chunk_embeddings = embeddings[i:i + batch_size]
        placeholders = []
        params = []

        for row, embedding in zip(chunk, chunk_embeddings):
            placeholders.append("(?, ?, vector(?))")
            params.extend([video_id, row["start"], json.dumps(embedding)])

        if placeholders:
            sql = "INSERT INTO transcript_embeddings (video_id, start_time, embedding) VALUES "
            sql += ", ".join(placeholders)
            statements.append(libsql_client.Statement(sql, params))

    client.batch(statements)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Voyage embeddings for existing transcripts.")
    parser.add_argument("--limit-videos", type=int, default=25, help="Maximum videos to process in this run.")
    parser.add_argument("--embed-batch-size", type=int, default=128, help="Texts per Voyage embedding request.")
    parser.add_argument("--insert-batch-size", type=int, default=50, help="Embeddings per DB insert batch.")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds to pause between Voyage calls.")
    args = parser.parse_args()

    api_key = os.environ.get("VOYAGE_API_KEY")
    db_url = os.environ.get("TURSO_DATABASE_URL")
    if not api_key:
        console.print("[bold red]❌ VOYAGE_API_KEY is missing in .env[/bold red]")
        sys.exit(1)
    if not db_url or "turso.io" not in db_url:
        console.print("[bold red]❌ TURSO_DATABASE_URL must point to Turso for vector embeddings.[/bold red]")
        sys.exit(1)

    console.print(Panel("[bold cyan]🚀 Assabiqoon Semantic Embeddings (Voyage AI)[/bold cyan]\n"
                        "[dim]Processing video transcripts to generate vector embeddings...[/dim]", 
                        border_style="cyan"))

    client = get_db_client()
    ensure_tables(client)
    checkpoint = load_checkpoint()
    done = set(checkpoint.get("done_video_ids", []))

    video_ids = [vid for vid in fetch_video_ids(client, args.limit_videos * 2) if vid not in done]
    video_ids = video_ids[:args.limit_videos]

    if not video_ids:
        console.print("[bold green]✨ All videos have embeddings! Nothing to do.[/bold green]")
        return

    console.print(f"[bold yellow]Found {len(video_ids)} videos to embed![/bold yellow]\n")
    
    success = 0
    failed = 0
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        
        overall_task = progress.add_task("[bold cyan]Overall Progress", total=len(video_ids))
        
        for index, video_id in enumerate(video_ids, start=1):
            rows = fetch_transcript_rows(client, video_id)
            texts = [row["text"] or "" for row in rows]
            embeddings = []
            
            if not texts:
                progress.update(overall_task, advance=1)
                continue

            video_task = progress.add_task(f"[yellow]Embedding {video_id} ({len(texts)} segments)[/yellow]", total=len(texts))

            for start in range(0, len(texts), args.embed_batch_size):
                batch_texts = texts[start:start + args.embed_batch_size]
                batch_embeddings = generate_embeddings_voyage(batch_texts, api_key)
                
                if batch_embeddings:
                    embeddings.extend(batch_embeddings)
                    progress.update(video_task, advance=len(batch_texts))
                else:
                    # Failed to get embeddings for this batch (likely rate limit retries exhausted)
                    break
                    
                time.sleep(args.sleep)

            if len(embeddings) == len(rows):
                progress.update(video_task, description=f"[green]Saving {video_id} to database...[/green]")
                save_embeddings(client, video_id, rows, embeddings, args.insert_batch_size)
                
                done.add(video_id)
                checkpoint["done_video_ids"] = sorted(done)
                checkpoint["last_video_id"] = video_id
                checkpoint["updated_at"] = time.time()
                save_checkpoint(checkpoint)
                
                success += 1
                progress.update(video_task, description=f"[bold green]✅ {video_id} Complete![/bold green]", completed=len(texts))
            else:
                failed += 1
                progress.update(video_task, description=f"[bold red]❌ {video_id} Failed (Got {len(embeddings)}/{len(rows)})[/bold red]")

            progress.update(overall_task, advance=1)
            time.sleep(1)

    # Final Summary
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    summary = Table(title="📊 Embedding Summary", show_header=True, header_style="bold cyan", border_style="cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right", style="bold green")
    summary.add_row("✅ Success", str(success))
    summary.add_row("❌ Failed", str(failed))
    summary.add_row("⏱️ Total Time", f"{minutes}m {seconds}s")
    console.print("\n")
    console.print(summary)
    
    client.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warning]🛑 Process stopped by user.[/warning]")
