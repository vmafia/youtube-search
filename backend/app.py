import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import html

from backend.config import Config
from backend.utils.youtube import YouTubeClient
from backend.utils.search import search_transcript, check_and_convert_milliseconds, expand_query

# Setup Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)

# File log handler (disabled in Vercel Serverless environment)
if not Config.IS_VERCEL:
    file_handler = RotatingFileHandler(
        Config.LOG_FILE, maxBytes=10000000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.WARNING)  # Log warnings and errors to file
    logger.addHandler(file_handler)

# Console log handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

app = Flask(__name__)
app.config.from_object(Config)

# Enable CORS (allow specific origin if specified, else allow all for dev)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Flask-Limiter for Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[Config.RATELIMIT_DEFAULT],
    storage_uri="memory://"
)

youtube_client = YouTubeClient(api_key=Config.YOUTUBE_API_KEY)

def sanitize_input(value: str) -> str:
    """Escapes string inputs to prevent XSS."""
    if not isinstance(value, str):
        return ""
    return html.escape(value.strip())

@app.errorhandler(Exception)
def handle_global_error(error):
    """Global error handler returning standard JSON format."""
    # Check if it's a limiter error
    if hasattr(error, 'code') and error.code == 429:
        logger.warning(f"Rate limit exceeded by {get_remote_address()}")
        return jsonify({
            "error": "Rate limit exceeded. Maximum 30 requests per minute.",
            "status_code": 429
        }), 429

    # Check for specific ValueError (often user errors)
    if isinstance(error, ValueError):
        logger.warning(f"Bad Request: {str(error)}")
        return jsonify({
            "error": str(error),
            "status_code": 400
        }), 400

    # Default server error
    logger.exception(f"Unhandled Exception: {str(error)} | Path: {request.path} | Method: {request.method}")
    return jsonify({
        "error": "Internal server error. Please try again later.",
        "status_code": 500
    }), 500

@app.route("/api/health", methods=["GET"])
@limiter.exempt  # Health check exempt from rate limiting
def health():
    return jsonify({
        "status": "healthy",
        "database": "firebase" if youtube_client.db_manager.use_firebase else "local_cache",
        "firebase_env_present": os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON") is not None,
        "firebase_init_error": youtube_client.db_manager.init_error
    }), 200

@app.route("/api/channel-videos", methods=["POST"])
def get_channel_videos():
    data = request.get_json() or {}
    channel_name = sanitize_input(data.get("channel_name", ""))
    
    if not channel_name:
        raise ValueError("channel_name parameter is required")
        
    try:
        limit = data.get("limit", 5000)
        videos = youtube_client.fetch_channel_videos(channel_name, limit=limit)
        return jsonify({"videos": videos}), 200
    except Exception as e:
        logger.error(f"Error fetching channel videos for {channel_name}: {str(e)}")
        raise e

@app.route("/api/video-transcript", methods=["POST"])
def get_video_transcript():
    data = request.get_json() or {}
    video_id = sanitize_input(data.get("video_id", ""))
    
    if not video_id:
        raise ValueError("video_id parameter is required")
        
    try:
        transcript = youtube_client.fetch_video_transcript(video_id)
        transcript = check_and_convert_milliseconds(transcript)
        return jsonify({"video_id": video_id, "transcript": transcript}), 200
    except Exception as e:
        logger.error(f"Error fetching transcript for video {video_id}: {str(e)}")
        raise e

@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json() or {}
    video_ids = data.get("video_ids", [])
    query = sanitize_input(data.get("query", ""))
    threshold = data.get("threshold", 80.0)
    
    if not query:
        raise ValueError("query parameter is required")
    if not video_ids or not isinstance(video_ids, list):
        raise ValueError("video_ids parameter is required and must be a list")

    # Expand query using local synonyms + Gemini AI (if available)
    gemini_key = Config.GEMINI_API_KEY
    expanded_queries = expand_query(query, api_key=gemini_key)
    logger.info(f"Search request: '{query}'. Expanded queries: {expanded_queries}")

    results = []
    channel_name = sanitize_input(data.get("channel_name", "@AssabiqoonPublisher"))

    # ─── Step 1: Optional speedup — ใช้ YouTube Search API หา video ที่น่าจะเกี่ยวข้อง
    # ไม่ใช้เป็น gate หลัก แต่ใช้เป็นข้อมูลเสริม (title/thumbnail) และ
    # ช่วย prioritize การดึง transcript ของ video ที่ยังไม่มีใน cache
    yt_meta = {}  # {video_id: {title, thumbnail}}
    yt_candidates_ids = set()  # video ที่ YouTube Search API คิดว่าเกี่ยวข้อง
    if youtube_client.api_key:
        try:
            matched = youtube_client.search_youtube_api(channel_name, query, max_results=100)
            video_ids_set = set(video_ids)
            for m in matched:
                if m["id"] in video_ids_set:
                    yt_meta[m["id"]] = {"title": m["title"], "thumbnail": m["thumbnail"]}
                    yt_candidates_ids.add(m["id"])
            logger.info(f"YouTube Search API returned {len(yt_candidates_ids)} candidates within the video list.")
        except Exception as e:
            logger.warning(f"YouTube Search API failed (non-critical): {str(e)}")

    # ─── Step 2: ค้นหา transcript จาก DB โดยตรงทุก video_id แบ่งเป็น batch
    # ไม่พึ่ง YouTube Search API เป็นตัวกรองหลัก เพื่อให้ได้ผลลัพธ์ครบถ้วน
    BATCH_SIZE = 50
    processed = set()

    for i in range(0, len(video_ids), BATCH_SIZE):
        batch = video_ids[i : i + BATCH_SIZE]
        for vid in batch:
            vid = sanitize_input(vid)
            if not vid or vid in processed:
                continue
            processed.add(vid)

            try:
                transcript = youtube_client.db_manager.get_document("transcripts", vid)

                # ถ้าไม่มีใน cache ให้พยายามดึง:
                # - ถ้าอยู่ใน Vercel → ดึงเฉพาะ video ที่ YouTube API บอกว่าเกี่ยวข้อง (ประหยัด quota + เวลา)
                # - ถ้ารันใน local → ดึงทุก video ที่ไม่มีใน cache
                if not transcript:
                    should_fetch = (not Config.IS_VERCEL) or (vid in yt_candidates_ids)
                    if should_fetch:
                        try:
                            transcript = youtube_client.fetch_video_transcript(vid)
                        except Exception as fetch_err:
                            logger.warning(f"Could not fetch transcript for {vid}: {fetch_err}")

                if not transcript:
                    # ไม่มี transcript เลย — ถ้าอยู่ใน yt_candidates ให้ mark ว่า missing
                    if vid in yt_candidates_ids:
                        meta = yt_meta[vid]
                        results.append({
                            "video_id": vid,
                            "matches": [],
                            "title": meta["title"],
                            "thumbnail": meta["thumbnail"],
                            "transcript_missing": True
                        })
                    continue

                matches = search_transcript(transcript, expanded_queries, threshold=threshold)
                if matches:
                    meta = yt_meta.get(vid, {})
                    result = {
                        "video_id": vid,
                        "matches": matches,
                        "thumbnail": meta.get(
                            "thumbnail",
                            f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
                        )
                    }
                    if meta.get("title"):
                        result["title"] = meta["title"]
                    results.append(result)

            except Exception as e:
                logger.warning(f"Skipping video {vid} during search: {str(e)}")
                continue

    logger.info(f"Search complete: '{query}' — {len(results)} video(s) matched out of {len(video_ids)} searched.")
    return jsonify({
        "query": query,
        "expanded_queries": expanded_queries,
        "results": results
    }), 200


@app.route("/api/bulk-index", methods=["POST"])
def bulk_index():
    """
    Pre-indexes transcripts for a list of video IDs into Firebase/local cache.
    ใช้สำหรับ batch ดึง transcript ล่วงหน้า ก่อนที่ผู้ใช้จะค้นหา
    เพื่อให้การค้นหาในอนาคตครอบคลุมทุกคลิปและเร็วขึ้น
    """
    if Config.IS_VERCEL:
        return jsonify({"error": "Bulk indexing is not supported on Vercel (timeout limit). Run locally."}), 400

    data = request.get_json() or {}
    video_ids = data.get("video_ids", [])
    channel_name = sanitize_input(data.get("channel_name", ""))

    # ถ้าไม่ส่ง video_ids แต่ส่ง channel_name ให้ดึง video list จาก channel นั้น
    if not video_ids and channel_name:
        try:
            videos = youtube_client.fetch_channel_videos(channel_name, limit=5000)
            video_ids = [v["id"] for v in videos]
            logger.info(f"Bulk index: resolved {len(video_ids)} videos from channel '{channel_name}'")
        except Exception as e:
            raise ValueError(f"Could not fetch channel videos for '{channel_name}': {str(e)}")

    if not video_ids:
        raise ValueError("video_ids หรือ channel_name is required")

    # จำกัด batch ไว้ที่ 500 ต่อครั้ง
    video_ids = video_ids[:500]
    indexed = []
    already_cached = []
    failed = []

    for vid in video_ids:
        vid = sanitize_input(vid)
        if not vid:
            continue
        try:
            existing = youtube_client.db_manager.get_document("transcripts", vid)
            if existing:
                already_cached.append(vid)
                continue
            transcript = youtube_client.fetch_video_transcript(vid)
            if transcript:
                indexed.append(vid)
            else:
                failed.append(vid)
        except Exception as e:
            logger.warning(f"bulk_index: failed for {vid}: {str(e)}")
            failed.append(vid)

    logger.info(
        f"Bulk index done: {len(indexed)} indexed, "
        f"{len(already_cached)} already cached, {len(failed)} failed."
    )
    return jsonify({
        "indexed": indexed,
        "already_cached": already_cached,
        "failed": failed,
        "summary": {
            "total": len(video_ids),
            "indexed": len(indexed),
            "already_cached": len(already_cached),
            "failed": len(failed)
        }
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
