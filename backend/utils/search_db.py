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
        raise ValueError("Missing TURSO_DATABASE_URL or TURSO_AUTH_TOKEN in .env")
        
    return libsql_client.create_client_sync(url=db_url, auth_token=auth_token)

def search_sqlite_fts(query: str, limit: int = 50, video_ids: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search using Turso FTS5.
    If video_ids is provided, filter by those videos.
    Returns results grouped by video_id with matched snippets.
    """
    try:
        client = get_db_client()
    except Exception as e:
        logger.error(f"Cannot connect to Turso DB: {e}")
        return []
        
    # Clean the query for FTS5 (remove quotes, special chars)
    from backend.utils.search import normalize_text
    
    clean_query = query.replace('"', '').replace("'", "")
    raw_terms = [term for term in clean_query.split() if term]
    if not raw_terms:
        return []
        
    # Normalize each term so that FTS5 MATCH works against norm_text column
    normalized_terms = [normalize_text(term) for term in raw_terms]
    normalized_terms = [term for term in normalized_terms if term]
    if not normalized_terms:
        normalized_terms = raw_terms
        
    fts_query = " AND ".join(f'"{term}"*' for term in normalized_terms)
    
    video_filter = ""
    params = [fts_query]
    
    if video_ids:
        placeholders = ",".join("?" * len(video_ids))
        video_filter = f" AND video_id IN ({placeholders})"
        params.extend(video_ids)
        
    sql = f"""
        SELECT 
            video_id, 
            start_time, 
            timestamp, 
            text, 
            bm25(transcripts_fts) as score
        FROM transcripts_fts
        WHERE transcripts_fts MATCH ?
        {video_filter}
        ORDER BY score
        LIMIT {limit * 3}
    """
    
    try:
        rs = client.execute(sql, params)
        rows = rs.rows
        
        # If FTS MATCH returned no rows, fallback to substring LIKE query in the normalized column
        if not rows and normalized_terms:
            like_conditions = []
            like_params = []
            for term in normalized_terms:
                like_conditions.append("norm_text LIKE ?")
                like_params.append(f"%{term}%")
                
            like_video_filter = ""
            query_params = like_params
            if video_ids:
                placeholders = ",".join("?" * len(video_ids))
                like_video_filter = f" AND video_id IN ({placeholders})"
                query_params = like_params + video_ids
                
            fallback_sql = f"""
                SELECT 
                    video_id, 
                    start_time, 
                    timestamp, 
                    text, 
                    0 as score
                FROM transcripts_fts
                WHERE {" AND ".join(like_conditions)}
                {like_video_filter}
                LIMIT {limit * 3}
            """
            logger.info(f"FTS MATCH yielded 0 results. Falling back to LIKE query for terms: {normalized_terms}")
            rs = client.execute(fallback_sql, query_params)
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
        
        if vid not in grouped_results:
            grouped_results[vid] = {
                "video_id": vid,
                "max_score": 0,
                "matches": []
            }
        
        # Calculate a normalized score for UI consistency.
        score_val = abs(score)
        ui_score = 90 + min(10, 100 / (score_val + 0.1)) 
        
        grouped_results[vid]["matches"].append({
            "timestamp": timestamp,
            "start": start_time,
            "text": text,
            "score": ui_score
        })
        
        if ui_score > grouped_results[vid]["max_score"]:
            grouped_results[vid]["max_score"] = ui_score
            
    # Sort by max_score and limit
    results = list(grouped_results.values())
    results.sort(key=lambda x: x["max_score"], reverse=True)
    
    return results[:limit]

def get_db_stats() -> Dict[str, Any]:
    try:
        client = get_db_client()
        
        rs = client.execute("SELECT COUNT(DISTINCT video_id) as count FROM transcripts_fts")
        transcribed_count = rs.rows[0][0]
        
        rs = client.execute("SELECT DISTINCT video_id FROM transcripts_fts")
        transcribed_ids = [row[0] for row in rs.rows]
        
        client.close()
        
        return {
            "total_videos": transcribed_count,
            "transcribed_count": transcribed_count,
            "transcribed_ids": transcribed_ids
        }
    except Exception as e:
        logger.error(f"Error getting Turso DB stats: {e}")
        return {
            "total_videos": 0,
            "transcribed_count": 0,
            "transcribed_ids": []
        }
