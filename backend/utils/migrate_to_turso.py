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
    
    db_url = os.environ.get("TURSO_DATABASE_URL")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not db_url or not auth_token:
        print("Missing TURSO credentials in .env")
        return

    print("Connecting to Turso...")
    client = libsql_client.create_client(url=db_url, auth_token=auth_token)
    
    print("Creating FTS5 table...")
    await client.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts 
        USING fts5(video_id UNINDEXED, start_time UNINDEXED, timestamp UNINDEXED, text, norm_text)
    """)
    
    # Check if data already exists
    rs = await client.execute("SELECT COUNT(*) as count FROM transcripts_fts")
    count = rs.rows[0][0]
    if count > 0:
        print(f"Table already has {count} rows. Dropping and recreating for a clean migration...")
        await client.execute("DROP TABLE transcripts_fts")
        await client.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts 
            USING fts5(video_id UNINDEXED, start_time UNINDEXED, timestamp UNINDEXED, text, norm_text)
        """)

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "all_transcripts.json.gz")
    if not os.path.exists(data_path):
        print(f"File not found: {data_path}")
        return
        
    print(f"Loading {data_path}...")
    with gzip.open(data_path, "rt", encoding="utf-8") as f:
        all_data = json.load(f)
        
    total_videos = len(all_data)
    print(f"Found {total_videos} videos. Starting migration...")
    
    # Batch size for inserts
    BATCH_SIZE = 200
    queries = []
    
    videos_processed = 0
    start_time = time.time()
    
    for vid, transcript in all_data.items():
        for line in transcript:
            start_sec = line.get("start", 0)
            if start_sec > 100000: start_sec /= 1000.0
            
            h = int(start_sec // 3600)
            m = int((start_sec % 3600) // 60)
            s = int(start_sec % 60)
            timestamp = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
            
            queries.append(libsql_client.Statement(
                "INSERT INTO transcripts_fts (video_id, start_time, timestamp, text, norm_text) VALUES (?, ?, ?, ?, ?)",
                [vid, start_sec, timestamp, line.get("text", ""), line.get("norm_text", "")]
            ))
            
            if len(queries) >= BATCH_SIZE:
                await client.batch(queries)
                queries = []
                await asyncio.sleep(0.1)
                
        videos_processed += 1
        if videos_processed % 50 == 0:
            elapsed = time.time() - start_time
            print(f"Processed {videos_processed}/{total_videos} videos... ({elapsed:.1f}s)")
            
    # Flush remaining
    if queries:
        await client.batch(queries)
        
    print("Migration complete! Optimizing index...")
    await client.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('optimize')")
    
    print("Initializing transcribed_videos helper table...")
    await client.execute("CREATE TABLE IF NOT EXISTS transcribed_videos (video_id TEXT PRIMARY KEY)")
    await client.execute("INSERT OR IGNORE INTO transcribed_videos (video_id) SELECT DISTINCT video_id FROM transcripts_fts")
    
    rs = await client.execute("SELECT COUNT(*) as count FROM transcripts_fts")
    final_count = rs.rows[0][0]
    print(f"Database build complete! Total rows: {final_count}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
