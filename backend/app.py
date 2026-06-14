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

@app.route("/api/transcription-stats", methods=["GET"])
def get_transcription_stats():
    from backend.utils.search_db import get_db_stats
    stats = get_db_stats()
    return jsonify(stats), 200

@app.route("/api/transcription-status", methods=["GET"])
def get_transcription_status():
    status_path = os.path.join(app.config["CACHE_DIR"], "transcription_status.json")
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"error": f"Failed to read status file: {str(e)}"}), 500
    else:
        return jsonify({
            "status": "idle",
            "current_index": 0,
            "total_to_process": 0,
            "current_video_id": "",
            "current_video_title": "",
            "progress_state": "not_started",
            "success_count": 0,
            "fail_count": 0,
            "last_updated": 0
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


# Global in-memory cache for transcripts
global_transcripts_cache = None

def load_all_transcripts():
    global global_transcripts_cache
    if global_transcripts_cache is not None:
        return global_transcripts_cache
        
    import gzip, json
    # Try writable cache dir first (e.g., /tmp on Vercel)
    path = os.path.join(youtube_client.db_manager.writable_cache_dir, "all_transcripts.json.gz")
    if not os.path.exists(path):
        # Fallback to bundled cache dir
        path = os.path.join(youtube_client.db_manager.bundled_cache_dir, "all_transcripts.json.gz")
        
    if os.path.exists(path):
        try:
            logger.info(f"Loading all_transcripts from {path} into memory...")
            with gzip.open(path, "rt", encoding="utf-8") as f:
                global_transcripts_cache = json.load(f)
            logger.info(f"Loaded {len(global_transcripts_cache)} transcripts into memory.")
        except Exception as e:
            logger.error(f"Failed to load global transcripts: {e}")
            global_transcripts_cache = {}
    else:
        logger.warning("all_transcripts.json.gz not found anywhere!")
        global_transcripts_cache = {}
        
    return global_transcripts_cache

@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json() or {}
    video_ids = data.get("video_ids", [])
    query = sanitize_input(data.get("query", ""))
    
    if not query:
        raise ValueError("query parameter is required")

    gemini_key = Config.GEMINI_API_KEY
    expanded_queries = expand_query(query, api_key=gemini_key)
    logger.info(f"Search request: '{query}'. Expanded queries: {expanded_queries}")

    from backend.utils.search_db import search_sqlite_fts
    # Use the first term for FTS5 (FTS5 handles multiple keywords easily)
    search_term = " ".join(expanded_queries)
    results = search_sqlite_fts(search_term, limit=50, video_ids=video_ids if video_ids else None)

    for r in results:
        r["thumbnail"] = f"https://img.youtube.com/vi/{r['video_id']}/mqdefault.jpg"
        # Best score is mapped correctly in search_db
        r["best_score"] = r["max_score"]

    logger.info(f"Search complete: '{query}' — {len(results)} videos returned.")
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

@app.route("/api/debug/cache", methods=["GET"])
def debug_cache():
    import os
    import sys
    cache_path = os.path.join(app.config["CACHE_DIR"], "transcripts")
    files = []
    if os.path.exists(cache_path):
        files = os.listdir(cache_path)
    return jsonify({
        "cache_path": cache_path,
        "exists": os.path.exists(cache_path),
        "files_count": len(files),
        "files_sample": files[:10],
        "sys_path": sys.path
    }), 200

@app.route("/api/chat", methods=["POST"])
@limiter.limit("15 per minute")
def chat():
    from backend.utils.llm import generate_completion
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        messages = data.get("messages", [])
        if not messages:
            return jsonify({"error": "Messages array is required"}), 400
            
        # Get the latest user question
        last_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
        if not last_message:
            return jsonify({"error": "No user message found"}), 400

        # Optional: Channel filter
        channel_name = data.get("channel_name", "").strip()

        # Step 1: Extract keywords from the question using the LLM itself
        # This is a simple trick to build RAG without a Vector DB!
        keyword_prompt = [
            {"role": "system", "content": "Extract 1 to 3 search keywords from the user's question to search a database of YouTube transcripts. Output ONLY the keywords separated by spaces. Do not output anything else. Example output: บาปใหญ่ นบีปลอม"},
            {"role": "user", "content": last_message}
        ]
        
        # We wrap this in a try-catch so if LLM fails, we just fallback to the original question as keyword
        keywords = last_message
        try:
            extracted = generate_completion(keyword_prompt, temperature=0.1)
            if extracted and len(extracted) < 50:
                keywords = extracted.strip()
        except Exception as e:
            logger.warning(f"Keyword extraction failed, using original question: {e}")

        # Step 2: Search transcripts
        logger.info(f"RAG searching for keywords: {keywords}")
        
        from backend.utils.search_db import search_sqlite_fts
        
        # We search the SQLite FTS database directly! Lightning fast.
        results = search_sqlite_fts(keywords, limit=5)
        
        top_matches = results
        context_text = ""
        
        if top_matches:
            context_text = "อ้างอิงจากข้อมูลซับไตเติ้ลในฐานข้อมูล:\n"
            for r in top_matches:
                vid = r["video_id"]
                for m in r["matches"][:2]: # take top 2 snippets per video
                    context_text += f"- วิดีโอ {vid} (นาทีที่ {m['timestamp']}): \"{m['text']}\"\n"
        else:
            context_text = "ไม่มีข้อมูลในฐานข้อมูลที่ตรงกับคำถามนี้"

        # Step 3: Build the final prompt and call the LLM
        system_prompt = f"""คุณคือผู้ช่วย AI ผู้เชี่ยวชาญด้านอิสลามศึกษา คุณมีหน้าที่ตอบคำถามโดยอ้างอิงจากบริบทข้อมูลซับไตเติ้ลวิดีโอ (YouTube Transcripts) ที่ระบบค้นหามาให้เท่านั้น
        
บริบทข้อมูลที่ค้นหาพบ:
{context_text}

กฎในการตอบ:
1. ให้ตอบคำถามโดยอิงจาก 'บริบทข้อมูลที่ค้นหาพบ' เป็นหลัก
2. หากในบริบทข้อมูลไม่มีเนื้อหาที่ตอบคำถามได้ ให้ตอบตรงๆ ว่า "ไม่พบข้อมูลนี้ในฐานข้อมูลคลิปวิดีโอ" หรือใช้ความรู้ทั่วไปเสริมได้เล็กน้อยแต่ต้องบอกให้ชัดเจน
3. ห้ามแต่งเติมข้อมูลที่บิดเบือนจากหลักศาสนา
4. ใช้ภาษาที่สุภาพ เป็นธรรมชาติ และเข้าใจง่าย
5. หากมีการอ้างอิงวิดีโอ ให้บอกด้วยว่าพบในวิดีโอ ID ใด (เช่น วิดีโอ id xyz นาทีที่ 12:30)
"""
        
        # Inject our system prompt at the beginning of the conversation
        final_messages = [{"role": "system", "content": system_prompt}]
        
        # We only pass the last 5 messages to save tokens and context limit
        final_messages.extend(messages[-5:])
        
        # Generate the final answer using streaming
        answer_stream = generate_completion(final_messages, temperature=0.7, stream=True)
        
        from flask import Response, stream_with_context
        import json
        
        def generate():
            # First yield the context used so frontend can display it
            initial_data = {
                "type": "context",
                "context_used": top_matches,
                "keywords_searched": keywords
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            # Then yield chunks of the answer
            for chunk in answer_stream:
                if chunk:
                    chunk_data = {"type": "chunk", "content": chunk}
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    
            # Finally send done
            yield f"data: [DONE]\n\n"
            
        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    except Exception as e:
        logger.exception("Chat API Error")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
