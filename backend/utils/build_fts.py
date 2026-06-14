import os
import sqlite3
import json
import gzip
import logging
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_convert_milliseconds(val):
    if val > 100000:
        return val / 1000.0
    return val

def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def build_fts_db(cache_dir="backend/cache", db_path="backend/cache/search.db"):
    transcripts_path = os.path.join(cache_dir, "all_transcripts.json.gz")
    videos_path = os.path.join(cache_dir, "channel_videos", "channel_videos__AssabiqoonPublisher_5000.json.gz")
    
    if not os.path.exists(transcripts_path):
        logger.error(f"Transcripts file not found: {transcripts_path}")
        return
        
    logger.info(f"Creating database at {db_path}...")
    
    # Remove existing db if it exists
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Create Videos Table
    c.execute("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            published_at TEXT,
            thumbnails TEXT
        )
    """)
    
    # 2. Create FTS5 Virtual Table for Transcripts
    # Using unicode61 tokenizer to handle Thai characters decently
    c.execute("""
        CREATE VIRTUAL TABLE transcripts_fts USING fts5(
            video_id UNINDEXED,
            start_time UNINDEXED,
            timestamp UNINDEXED,
            text,
            norm_text,
            tokenize='unicode61'
        )
    """)
    
    # Load and insert videos
    if os.path.exists(videos_path):
        logger.info("Loading videos metadata...")
        with gzip.open(videos_path, 'rt', encoding='utf-8') as f:
            videos = json.load(f)
            for v in videos:
                c.execute(
                    "INSERT OR REPLACE INTO videos (video_id, title, published_at, thumbnails) VALUES (?, ?, ?, ?)",
                    (v.get("id", ""), v.get("title", ""), v.get("publishedAt", ""), json.dumps(v.get("thumbnails", {})))
                )
    
    # Load and insert transcripts
    logger.info("Loading and indexing transcripts. This might take a minute...")
    with gzip.open(transcripts_path, 'rt', encoding='utf-8') as f:
        all_transcripts = json.load(f)
        
        for vid, lines in tqdm(all_transcripts.items(), desc="Indexing videos"):
            for line in lines:
                start_sec = check_and_convert_milliseconds(line.get("start", 0))
                timestamp = format_timestamp(start_sec)
                
                c.execute(
                    "INSERT INTO transcripts_fts (video_id, start_time, timestamp, text, norm_text) VALUES (?, ?, ?, ?, ?)",
                    (vid, start_sec, timestamp, line.get("text", ""), line.get("norm_text", ""))
                )
                
    conn.commit()
    
    # Run optimize
    logger.info("Optimizing FTS index...")
    c.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('optimize')")
    conn.commit()
    conn.close()
    
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    logger.info(f"Database build complete! Size: {db_size:.2f} MB")

if __name__ == "__main__":
    build_fts_db()
