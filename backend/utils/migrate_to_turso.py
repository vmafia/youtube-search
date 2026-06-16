import os
import json
import gzip
import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

# We might not have libsql_client installed yet, so we import inside the function
async def migrate():
    import libsql_client
    from backend.utils.search import normalize_text
    
    db_url = os.environ.get("TURSO_DATABASE_URL")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not db_url or not auth_token:
        print("Missing TURSO credentials in .env")
        return
 
    print("Connecting to Turso...")
    client = libsql_client.create_client(url=db_url, auth_token=auth_token)
    
    print("Creating transcripts tables and indexes...")
    await client.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            video_id TEXT,
            start_time REAL,
            timestamp TEXT,
            text TEXT,
            norm_text TEXT
        )
    """)
    await client.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_video_start ON transcripts(video_id, start_time)")
    await client.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_video_id ON transcripts(video_id)")

    await client.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts 
        USING fts5(video_id UNINDEXED, start_time UNINDEXED, timestamp UNINDEXED, text, norm_text)
    """)
    
    # Fetch already processed videos to resume
    rs = await client.execute("SELECT DISTINCT video_id FROM transcripts")
    existing_videos = set(row[0] for row in rs.rows)
    print(f"Found {len(existing_videos)} videos already in the database. Resuming from where we left off...")
 
    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "all_transcripts.json.gz")
    if not os.path.exists(data_path):
        print(f"File not found: {data_path}")
        return
        
    print(f"Loading {data_path}...")
    with gzip.open(data_path, "rt", encoding="utf-8") as f:
        all_data = json.load(f)
        
    total_videos = len(all_data)
    print(f"Found {total_videos} videos. Starting migration...")
    
    # Batch size for inserts (we insert in pairs, so limit statements to 200 per batch)
    BATCH_SIZE = 100
    queries = []
    
    videos_processed = 0
    start_time = time.time()
    
    for vid, transcript in all_data.items():
        if vid in existing_videos:
            continue
        for line in transcript:
            start_sec = line.get("start", 0)
            if start_sec > 100000: start_sec /= 1000.0
            
            h = int(start_sec // 3600)
            m = int((start_sec % 3600) // 60)
            s = int(start_sec % 60)
            timestamp = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
            
            text_val = line.get("text", "")
            norm_text_val = line.get("norm_text") or normalize_text(text_val)
            
            queries.append(libsql_client.Statement(
                "INSERT INTO transcripts (video_id, start_time, timestamp, text, norm_text) VALUES (?, ?, ?, ?, ?)",
                [vid, start_sec, timestamp, text_val, norm_text_val]
            ))
            queries.append(libsql_client.Statement(
                "INSERT INTO transcripts_fts (video_id, start_time, timestamp, text, norm_text) VALUES (?, ?, ?, ?, ?)",
                [vid, start_sec, timestamp, text_val, norm_text_val]
            ))
            
            if len(queries) >= BATCH_SIZE * 2:
                retries = 3
                while retries > 0:
                    try:
                        await client.batch(queries)
                        break
                    except Exception as e:
                        print(f"Batch insert failed, retrying... ({e})")
                        retries -= 1
                        await asyncio.sleep(2)
                if retries == 0:
                    raise Exception("Failed to insert batch after 3 retries")
                queries = []
                await asyncio.sleep(0.1)
                
        videos_processed += 1
        if videos_processed % 50 == 0:
            elapsed = time.time() - start_time
            print(f"Processed {videos_processed}/{total_videos} videos... ({elapsed:.1f}s)")
            
    # Flush remaining
    if queries:
        retries = 3
        while retries > 0:
            try:
                await client.batch(queries)
                break
            except Exception as e:
                print(f"Final batch insert failed, retrying... ({e})")
                retries -= 1
                await asyncio.sleep(2)
        if retries == 0:
            raise Exception("Failed to insert final batch after 3 retries")
        
    print("Migration complete! Optimizing index...")
    await client.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('optimize')")
    
    print("Initializing transcribed_videos helper table...")
    await client.execute("CREATE TABLE IF NOT EXISTS transcribed_videos (video_id TEXT PRIMARY KEY)")
    # Insert from standard table
    await client.execute("INSERT OR IGNORE INTO transcribed_videos (video_id) SELECT DISTINCT video_id FROM transcripts")
    
    rs = await client.execute("SELECT COUNT(*) as count FROM transcripts")
    final_count = rs.rows[0][0]
    print(f"Database build complete! Total rows: {final_count}")
    
    await client.close()
 
if __name__ == "__main__":
    asyncio.run(migrate())

