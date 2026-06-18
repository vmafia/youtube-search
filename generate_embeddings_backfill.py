import argparse
import json
import os
import time
from pathlib import Path

import libsql_client
from dotenv import load_dotenv

from backend.config import Config
from backend.utils.search_db import ensure_tables, get_db_client
from backend.utils.youtube import generate_embeddings_gemini

load_dotenv()

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
    rs = client.execute(
        """
        SELECT t.video_id
        FROM transcripts t
        LEFT JOIN transcript_embeddings e ON t.video_id = e.video_id
        GROUP BY t.video_id
        HAVING COUNT(e.start_time) = 0
        ORDER BY t.video_id
        LIMIT ?
        """,
        [limit],
    )
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
    parser = argparse.ArgumentParser(description="Backfill Gemini embeddings for existing transcripts.")
    parser.add_argument("--limit-videos", type=int, default=25, help="Maximum videos to process in this run.")
    parser.add_argument("--embed-batch-size", type=int, default=50, help="Texts per Gemini embedding request.")
    parser.add_argument("--insert-batch-size", type=int, default=50, help="Embeddings per DB insert batch.")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds to pause between Gemini calls.")
    args = parser.parse_args()

    api_key = Config.GEMINI_API_KEY
    db_url = os.environ.get("TURSO_DATABASE_URL")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing.")
    if not db_url or "turso.io" not in db_url:
        raise SystemExit("TURSO_DATABASE_URL must point to Turso for vector embeddings.")

    client = get_db_client()
    ensure_tables(client)
    checkpoint = load_checkpoint()
    done = set(checkpoint.get("done_video_ids", []))

    video_ids = [vid for vid in fetch_video_ids(client, args.limit_videos * 2) if vid not in done]
    video_ids = video_ids[:args.limit_videos]

    print(f"Embedding backfill: {len(video_ids)} videos queued")
    success = 0
    failed = 0

    for index, video_id in enumerate(video_ids, start=1):
        rows = fetch_transcript_rows(client, video_id)
        texts = [row["text"] or "" for row in rows]
        embeddings = []

        print(f"[{index}/{len(video_ids)}] {video_id}: {len(texts)} segments")
        for start in range(0, len(texts), args.embed_batch_size):
            batch_texts = texts[start:start + args.embed_batch_size]
            batch_embeddings = generate_embeddings_gemini(batch_texts, api_key)
            embeddings.extend(batch_embeddings)
            print(f"  embedded {len(embeddings)}/{len(texts)}")
            time.sleep(args.sleep)

            if len(batch_embeddings) != len(batch_texts):
                break

        if len(embeddings) != len(rows):
            failed += 1
            print(f"  skipped: got {len(embeddings)} embeddings, expected {len(rows)}")
            continue

        save_embeddings(client, video_id, rows, embeddings, args.insert_batch_size)
        done.add(video_id)
        checkpoint["done_video_ids"] = sorted(done)
        checkpoint["last_video_id"] = video_id
        checkpoint["updated_at"] = time.time()
        save_checkpoint(checkpoint)
        success += 1
        print("  saved")

    client.close()
    print(f"Done. success={success}, failed={failed}")


if __name__ == "__main__":
    main()
