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
    results = search_sqlite_fts(expanded_queries, limit=50, video_ids=video_ids if video_ids else None)

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
            
        # Sanitize messages list to prevent prompt injection and system instruction spoofing
        sanitized_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if not content or not isinstance(content, str):
                continue
            if role in ["user", "assistant"]:
                sanitized_messages.append({"role": role, "content": content})
            else:
                logger.warning(f"Filtered out suspicious message with role '{role}' from chat request.")
        
        if not sanitized_messages:
            return jsonify({"error": "Valid messages are required"}), 400
            
        # Get the latest user question
        last_message = next((m["content"] for m in reversed(sanitized_messages) if m["role"] == "user"), None)
        if not last_message:
            return jsonify({"error": "No user message found"}), 400

        # Optional: Channel filter
        channel_name = data.get("channel_name", "").strip()

        # Step 1: Extract keywords from the question using LLM for "ฉลาดเกินเบอร์" RAG
        # This prevents full table scans and handles Thai word boundaries natively,
        # taking ~0.5s but saving millions of DB reads and Vercel timeouts.
        extraction_prompt = [
            {"role": "system", "content": "You are a search query extractor. Extract 2 to 4 most important distinct keywords or short phrases from the user's question. Do not include question words (e.g. คือ, อะไร, ทำไม). Return ONLY the keywords separated by spaces. Example input: 'ตรรกศาสตร์ที่ใช้ได้และใช้ไม่ได้' -> Example output: 'ตรรกศาสตร์ ใช้ได้ ใช้ไม่ได้'"},
            {"role": "user", "content": last_message}
        ]
        
        try:
            llm_response = generate_completion(extraction_prompt, stream=False)
            if llm_response and "error" not in llm_response.lower():
                keywords = llm_response.strip()
                logger.info(f"LLM extracted keywords: {keywords}")
            else:
                keywords = last_message
        except Exception as e:
            logger.error(f"LLM keyword extraction failed: {e}")
            keywords = last_message
            
        # Fallback basic stopword removal just in case
        stopwords = ["คือ", "อะไร", "ไหม", "ครับ", "ค่ะ", "ช่วยบอก", 
"หน่อย", "อยากรู้", "เรื่อง", "ว่า", "ยังไง", "บ้าง", 
"ทำไม", "?", "ในคลิป", "อาจารย์"]
        for word in stopwords:
            keywords = keywords.replace(word, " ")
        keywords = " ".join(keywords.split())
        
        # Step 2: Search transcripts
        logger.info(f"RAG searching for keywords: {keywords}")
        
        from backend.utils.search_db import search_sqlite_fts
        
        # We search the SQLite FTS database directly! Lightning fast.
        results = search_sqlite_fts(keywords, limit=5)
        
        # If no results, retry by splitting keywords into individual words and OR-ing them
        if not results:
            words = [w for w in keywords.split() if len(w) > 1]
            if words:
                logger.info(f"RAG search with AND returned 0 results. Retrying with OR of words: {words}")
                results = search_sqlite_fts(words, limit=5)
        
        top_matches = results
        context_text = ""
        
        if top_matches:
            # Prepare matches for batch context fetching (window of 30 seconds before/after)
            context_items = []
            for r in top_matches:
                vid = r["video_id"]
                for m in r["matches"][:2]:
                    context_items.append({
                        "video_id": vid,
                        "start": m["start"],
                        "text": m["text"]
                    })
            
            from backend.utils.search_db import fetch_batch_surrounding_context
            context_map = fetch_batch_surrounding_context(context_items, window_seconds=30)
            
            context_text = "อ้างอิงจากข้อมูลซับไตเติ้ลในฐานข้อมูล:\n"
            for r in top_matches:
                vid = r["video_id"]
                for m in r["matches"][:2]:
                    merged_text = context_map.get((vid, m["start"]), m["text"])
                    context_text += f"- วิดีโอ {vid} (นาทีที่ {m['timestamp']}): \"{merged_text}\"\n"
        else:
            context_text = "ไม่มีข้อมูลในฐานข้อมูลที่ตรงกับคำถามนี้"

        # Step 3: Build the final prompt and call the LLM
        system_prompt = f"""คุณคือผู้ช่วย AI ผู้เชี่ยวชาญด้านอิสลามศึกษา คุณมีหน้าที่ตอบคำถามโดยอิงจากทั้ง 'บริบทข้อมูลซับไตเติ้ลวิดีโอ' และ 'ความรู้ทั่วไปเชิงลึก'
        
บริบทข้อมูลที่ค้นหาพบ:
{context_text}

กฎในการตอบ:
1. หากมีบริบทข้อมูล ให้ใช้อธิบายเป็นหลัก **และต้องระบุเสมอว่าอ้างอิงมาจากวิดีโอ ID ใด และช่วงเวลาใด (นาทีที่เท่าไหร่)** สอดแทรกไปในการอธิบายเพื่อให้ดูน่าเชื่อถือ
2. หากไม่มีบริบทข้อมูลที่ตรงกับคำถาม **ห้ามตอบแค่ว่า "ไม่พบข้อมูล" เด็ดขาด!** ให้คุณใช้ความรู้เชิงลึกของคุณอธิบายคำตอบอย่างละเอียดและฉลาดที่สุด (เสมือนอาจารย์กำลังสอน) แล้วค่อยทิ้งท้ายสั้นๆ ว่า "(หมายเหตุ: ค้นหาไม่พบเนื้อหานี้ในคลิปวิดีโอปัจจุบัน)"
3. ห้ามแต่งเติมข้อมูลที่บิดเบือนจากหลักศาสนา
4. ใช้ภาษาที่สุภาพ เป็นธรรมชาติ เข้าใจง่าย และลึกซึ้ง
5. ห้ามจัดรูปแบบ Markdown (เช่น ตัวหนา ตัวเอียง หรือหัวข้อ) ให้พิมพ์เว้นวรรคและขึ้นบรรทัดใหม่ธรรมดาเพื่อให้มนุษย์อ่านง่ายที่สุด
6. ห้ามสร้าง "ลิงก์ (URL)" วิดีโอด้วยตัวเองเด็ดขาด ให้พิมพ์บอกแค่วิดีโอ ID และเวลาเป็นข้อความธรรมดา
"""
        
        # Inject our system prompt at the beginning of the conversation
        final_messages = [{"role": "system", "content": system_prompt}]
        
        # We only pass the last 5 messages to save tokens and context limit
        final_messages.extend(sanitized_messages[-5:])
        
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
            yield f"data: {json.dumps(initial_data, ensure_ascii=False)}\n\n"
            
            try:
                # Then yield chunks of the answer
                for chunk in answer_stream:
                    if chunk:
                        chunk_data = {"type": "chunk", "content": chunk}
                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}")
                err_data = {"type": "chunk", "content": f"\n\n[ระบบขัดข้อง: เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI หรือถูกบล็อกโดย Safety Filter: {str(e)}]"}
                yield f"data: {json.dumps(err_data, ensure_ascii=False)}\n\n"
                
            # Finally send done
            yield f"data: [DONE]\n\n"
            
        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    except Exception as e:
        logger.exception("Chat API Error")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
