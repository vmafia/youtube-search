import os
import json
import time
from backend.utils.search_db import get_db_client
from backend.utils.youtube import generate_embeddings_gemini
from backend.config import Config
import libsql_client

video_id = "9PWN5ylMYo0"
print(f"Fixing embeddings for video {video_id}...")

client = get_db_client()

# Fetch transcript segments
res = client.execute("SELECT start_time, text FROM transcripts WHERE video_id = ? ORDER BY start_time ASC", [video_id])
segments = res.rows

print(f"Found {len(segments)} segments to embed.")

if len(segments) == 0:
    print("No segments found. Exiting.")
    client.close()
    exit()

# Generate embeddings
gemini_api_key = Config.GEMINI_API_KEY
texts_to_embed = [row[1] for row in segments]
embeddings = []
emb_batch_size = 100

for j in range(0, len(texts_to_embed), emb_batch_size):
    batch_texts = texts_to_embed[j:j+emb_batch_size]
    print(f"Embedding batch {j//emb_batch_size + 1}/{(len(texts_to_embed)-1)//emb_batch_size + 1}...")
    batch_embs = generate_embeddings_gemini(batch_texts, gemini_api_key)
    embeddings.extend(batch_embs)
    time.sleep(2) # brief pause to prevent hitting rate limit immediately

print(f"Successfully generated {len(embeddings)} / {len(segments)} embeddings.")

if len(embeddings) == len(segments):
    # Clear old embeddings if any
    client.execute("DELETE FROM transcript_embeddings WHERE video_id = ?", [video_id])
    
    # Batch insert
    queries = []
    batch_size = 50
    for j in range(0, len(segments), batch_size):
        chunk_segs = segments[j:j+batch_size]
        chunk_embs = embeddings[j:j+batch_size]
        
        sql = "INSERT INTO transcript_embeddings (video_id, start_time, embedding) VALUES "
        placeholders = []
        params = []
        for idx, row in enumerate(chunk_segs):
            start_sec = row[0]
            emb_val = chunk_embs[idx]
            placeholders.append("(?, ?, vector(?))")
            params.extend([video_id, start_sec, json.dumps(emb_val)])
            
        sql += ", ".join(placeholders)
        queries.append(libsql_client.Statement(sql, params))
        
    client.batch(queries)
    print("Successfully saved all embeddings to Turso!")
else:
    print("Failed to get all embeddings. Mismatch.")

client.close()
