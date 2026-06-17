import os
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def get_db_client():
    import libsql_client
    db_url = os.environ.get("TURSO_DATABASE_URL")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not db_url or not auth_token:
        # Fallback to local SQLite file database
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_db_path = os.path.join(base_dir, "backend", "cache", "search.db")
        os.makedirs(os.path.dirname(local_db_path), exist_ok=True)
        logger.info(f"Using local SQLite database at: {local_db_path}")
        return libsql_client.create_client_sync(url=f"file:{local_db_path}")
        
    return libsql_client.create_client_sync(url=db_url, auth_token=auth_token)

def ensure_tables(client):
    """Ensures that both the relational transcripts table (with indexes) and FTS table exist."""
    try:
        client.batch([
            "CREATE TABLE IF NOT EXISTS transcribed_videos (video_id TEXT PRIMARY KEY)",
            """CREATE TABLE IF NOT EXISTS transcripts (
                video_id TEXT,
                start_time REAL,
                timestamp TEXT,
                text TEXT,
                norm_text TEXT,
                speaker TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_transcripts_video_start ON transcripts(video_id, start_time)",
            "CREATE INDEX IF NOT EXISTS idx_transcripts_video_id ON transcripts(video_id)",
            """CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
                video_id UNINDEXED,
                start_time UNINDEXED,
                timestamp UNINDEXED,
                text,
                norm_text
            )"""
        ])
        
        # Try to dynamically add speaker column to transcripts relational table for compatibility
        try:
            client.execute("ALTER TABLE transcripts ADD COLUMN speaker TEXT")
        except Exception:
            pass
            
        # Dynamically create vector table and index if using remote Turso DB
        db_url = os.environ.get("TURSO_DATABASE_URL")
        if db_url and "turso.io" in db_url:
            try:
                client.execute("CREATE TABLE IF NOT EXISTS transcript_embeddings (video_id TEXT, start_time REAL, embedding F32_BLOB(768))")
                client.execute("CREATE INDEX IF NOT EXISTS idx_embeddings ON transcript_embeddings (libsql_vector_idx(embedding, 'metric=cosine'))")
                logger.info("Turso vector table and index verified/created.")
            except Exception as ve:
                logger.warning(f"Could not initialize Turso vector tables: {ve}")
                
        logger.info("Database tables and indexes verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to ensure database tables and indexes: {e}")

def search_sqlite_fts(query: Any, limit: int = 50, video_ids: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search using Turso FTS5.
    If video_ids is provided, filter by those videos.
    Returns results grouped by video_id with matched snippets.
    Supports single query string or list of query strings (synonyms/alternative queries).
    """
    try:
        client = get_db_client()
    except Exception as e:
        logger.error(f"Cannot connect to Turso DB: {e}")
        return []
        
    # Standardize input to list of query strings
    if isinstance(query, str):
        queries = [query]
    else:
        queries = query

    from backend.utils.search import normalize_text
    
    clauses = []
    like_clauses = []
    like_params = []
    
    for q in queries:
        clean_q = q.replace('"', '').replace("'", "")
        raw_terms = [term for term in clean_q.split() if term]
        if not raw_terms:
            continue
            
        # Normalize each term so that FTS5 MATCH works against norm_text column
        normalized_terms = [normalize_text(term) for term in raw_terms]
        normalized_terms = [term for term in normalized_terms if term]
        if not normalized_terms:
            normalized_terms = raw_terms
            
        # FTS5 clause: AND within words of a single synonym/query phrase
        clause = " AND ".join(f'"{term}"*' for term in normalized_terms)
        if len(normalized_terms) > 1:
            clauses.append(f"({clause})")
        else:
            clauses.append(clause)
            
        # Fallback LIKE clause: AND within words of a single synonym/query phrase
        sub_conditions = []
        for term in normalized_terms:
            sub_conditions.append("norm_text LIKE ?")
            like_params.append(f"%{term}%")
        if sub_conditions:
            like_clauses.append(f"({' AND '.join(sub_conditions)})")
            
    if not clauses:
        client.close()
        return []
        
    # OR between different synonyms/expanded query phrases
    fts_query = " OR ".join(clauses)
    
    video_filter = ""
    params = [fts_query]
    
    # Safeguard against SQLite parameter limit (too many SQL variables)
    if video_ids and len(video_ids) > 900:
        logger.info(f"Bypassing video_ids filter: length {len(video_ids)} is close to SQLite parameter limits.")
        video_ids = None
        
    if video_ids:
        placeholders = ",".join("?" * len(video_ids))
        video_filter = f" AND fts.video_id IN ({placeholders})"
        params.extend(video_ids)
        
    sql = f"""
        SELECT 
            fts.video_id, 
            fts.start_time, 
            fts.timestamp, 
            fts.text, 
            bm25(transcripts_fts) as score,
            t.speaker
        FROM transcripts_fts fts
        LEFT JOIN transcripts t ON fts.video_id = t.video_id AND fts.start_time = t.start_time
        WHERE transcripts_fts MATCH ?
        {video_filter}
        ORDER BY score
        LIMIT {limit * 3}
    """
    
    try:
        rs = client.execute(sql, params)
        rows = rs.rows
    except Exception as e:
        logger.error(f"Turso FTS5 error: {e}")
        return []
    finally:
        client.close()
        
    # Group by video_id
    grouped_results = {}
    for row in rows:
        vid = row[0]
        start_time = row[1]
        timestamp = row[2]
        text = row[3]
        score = row[4]
        speaker = row[5] if len(row) > 5 else None
        
        if vid not in grouped_results:
            grouped_results[vid] = {
                "video_id": vid,
                "max_score": 0,
                "matches": []
            }
        
        # Calculate a normalized score for UI consistency.
        if score < 0:
            # FTS5 BM25 score: more negative is better (e.g. -0.5 -> 91%, -5.0 -> 100%)
            score_val = -score
            ui_score = 90 + min(10, score_val * 2)
        else:
            # Fallback LIKE query has score = 0
            ui_score = 85.0
        
        grouped_results[vid]["matches"].append({
            "timestamp": timestamp,
            "start": start_time,
            "text": text,
            "score": ui_score,
            "speaker": speaker
        })
        
        if ui_score > grouped_results[vid]["max_score"]:
            grouped_results[vid]["max_score"] = ui_score
            
    # Sort by max_score and limit
    results = list(grouped_results.values())
    results.sort(key=lambda x: x["max_score"], reverse=True)
    
    return results[:limit]

def search_vector(query_embedding: List[float], limit: int = 50, video_ids: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search using Turso Vector Similarity.
    Queries the transcript_embeddings table using vector_top_k and returns results.
    """
    db_url = os.environ.get("TURSO_DATABASE_URL")
    if not db_url or not query_embedding:
        return []
        
    try:
        client = get_db_client()
    except Exception as e:
        logger.error(f"Cannot connect to Turso DB for vector search: {e}")
        return []
        
    video_filter = ""
    params = [json.dumps(query_embedding)]
    
    if video_ids and len(video_ids) > 900:
        video_ids = None
        
    if video_ids:
        placeholders = ",".join("?" * len(video_ids))
        video_filter = f" AND e.video_id IN ({placeholders})"
        params.extend(video_ids)
        
    # We use vector_top_k to do vector search. 
    # Since we need to get text, we join with the transcripts table.
    sql = f"""
        SELECT 
            e.video_id, 
            e.start_time, 
            t.timestamp, 
            t.text, 
            vector_distance_cos(e.embedding, vector(?)) as distance,
            t.speaker
        FROM transcript_embeddings e
        JOIN transcripts t ON e.video_id = t.video_id AND e.start_time = t.start_time
        WHERE vector_top_k(e.embedding, vector(?), {limit * 3})
        {video_filter}
        ORDER BY distance ASC
        LIMIT {limit * 3}
    """
    # Duplicate query embedding for both vector_distance_cos and vector_top_k
    import json
    params.insert(1, json.dumps(query_embedding))
    
    try:
        rs = client.execute(sql, params)
        rows = rs.rows
    except Exception as e:
        logger.error(f"Turso vector search error: {e}")
        return []
    finally:
        client.close()
        
    # Group results by video_id
    grouped_results = {}
    for row in rows:
        vid = row[0]
        start_time = row[1]
        timestamp = row[2]
        text = row[3]
        distance = row[4]
        speaker = row[5] if len(row) > 5 else None
        
        # Convert cosine distance to compatibility score (0.0 to 1.0, lower distance is better)
        score = (1.0 - (distance / 2.0)) * 100.0
        
        if vid not in grouped_results:
            grouped_results[vid] = {
                "video_id": vid,
                "max_score": 0,
                "matches": []
            }
            
        grouped_results[vid]["matches"].append({
            "timestamp": timestamp,
            "start": start_time,
            "text": text,
            "score": round(score, 1),
            "match_type": "semantic",
            "speaker": speaker
        })
        
        if score > grouped_results[vid]["max_score"]:
            grouped_results[vid]["max_score"] = score
            
    results = list(grouped_results.values())
    results.sort(key=lambda x: x["max_score"], reverse=True)
    return results[:limit]

def get_db_stats() -> Dict[str, Any]:
    try:
        client = get_db_client()
        
        # 1. Ensure the helper and standard tables exist
        ensure_tables(client)
        
        # 2. Perform one-time migration if the helper table is empty
        rs = client.execute("SELECT COUNT(*) FROM transcribed_videos")
        if rs.rows[0][0] == 0:
            logger.info("Migrating existing video IDs to transcribed_videos helper table...")
            # Query from transcripts standard table instead of transcripts_fts to prevent full table scan
            client.execute("INSERT OR IGNORE INTO transcribed_videos (video_id) SELECT DISTINCT video_id FROM transcripts")
            
        # 3. Query stats from the helper table (extremely cheap, scales to 1000s of videos in milliseconds)
        rs = client.execute("SELECT COUNT(*) FROM transcribed_videos")
        transcribed_count = rs.rows[0][0]
        
        rs = client.execute("SELECT video_id FROM transcribed_videos")
        transcribed_ids = [row[0] for row in rs.rows]
        
        client.close()
        
        return {
            "total_videos": transcribed_count,
            "transcribed_count": transcribed_count,
            "transcribed_ids": transcribed_ids
        }
    except Exception as e:
        logger.error(f"Error getting Turso DB stats: {e}")
        # Return None to signal DB error - callers must handle this
        # to avoid re-processing all videos when DB is unreachable
        return {
            "total_videos": -1,
            "transcribed_count": -1,
            "transcribed_ids": None,
            "error": str(e)
        }

def fetch_batch_surrounding_context(items: List[Dict[str, Any]], window_seconds: int = 120) -> Dict[tuple, str]:
    """
    items is a list of dicts containing 'video_id' and 'start'.
    Returns a dict mapping (video_id, start) to the merged surrounding text.
    Querying from standard transcripts table using index to prevent FTS5 full table scan.
    """
    if not items:
        return {}
        
    try:
        client = get_db_client()
    except Exception as e:
        logger.error(f"Cannot connect to Turso DB for batch context: {e}")
        return {}
        
    # Build conditions
    conditions = []
    params = []
    query_parts = []
    for item in items:
        vid = item["video_id"]
        start = item["start"]
        lower = max(0, start - window_seconds)
        upper = start + window_seconds
        query_parts.append("SELECT video_id, start_time, text FROM transcripts WHERE video_id = ? AND start_time >= ? AND start_time <= ?")
        params.extend([vid, lower, upper])
        
    sql = " UNION ALL ".join(query_parts)
    
    result_map = {}
    try:
        rs = client.execute(sql, params)
        # Group returned segments by video_id
        grouped = {}
        for row in rs.rows:
            vid, start_time, text = row[0], row[1], row[2]
            if vid not in grouped:
                grouped[vid] = []
            grouped[vid].append((start_time, text))
            
        # For each original item, find the segments that fall into its window
        for item in items:
            vid = item["video_id"]
            start = item["start"]
            lower = max(0, start - window_seconds)
            upper = start + window_seconds
            
            # Filter and sort segments in the window
            if vid in grouped:
                segments_in_window = [text for start_time, text in grouped[vid] if lower <= start_time <= upper]
                result_map[(vid, start)] = " ".join(segments_in_window)
            else:
                result_map[(vid, start)] = item.get("text", "")
                
        return result_map
    except Exception as e:
        logger.error(f"Error fetching batch surrounding context: {e}")
        return {}
    finally:
        client.close()
