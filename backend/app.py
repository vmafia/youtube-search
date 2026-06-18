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
    allow_live_fetch = bool(data.get("allow_live_fetch", False))
    
    if not video_id:
        raise ValueError("video_id parameter is required")
        
    try:
        cached_transcripts = load_all_transcripts()
        cached_transcript = cached_transcripts.get(video_id)
        if cached_transcript:
            transcript = check_and_convert_milliseconds(cached_transcript)
            return jsonify({"video_id": video_id, "transcript": transcript, "source": "cache"}), 200

        cached_transcript = youtube_client.db_manager.get_document("transcripts", video_id)
        if cached_transcript:
            transcript = check_and_convert_milliseconds(cached_transcript)
            return jsonify({"video_id": video_id, "transcript": transcript, "source": "document_cache"}), 200

        if not allow_live_fetch:
            return jsonify({
                "error": "ยังไม่มีสคริปต์นี้ในแคช กรุณารันงานจัดทำดัชนีสคริปต์ก่อนเปิดฉบับเต็ม",
                "status_code": 404
            }), 404

        transcript = youtube_client.fetch_video_transcript(video_id)
        transcript = check_and_convert_milliseconds(transcript)
        return jsonify({"video_id": video_id, "transcript": transcript, "source": "live"}), 200
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
@limiter.limit("30 per minute")
def search():
    data = request.get_json() or {}
    video_ids = data.get("video_ids", [])
    query = sanitize_input(data.get("query", ""))
    
    if not query:
        raise ValueError("query parameter is required")

    gemini_key = Config.GEMINI_API_KEY
    expanded_queries = expand_query(query, api_key=gemini_key)
    logger.info(f"Search request: '{query}'. Expanded queries: {expanded_queries}")

    # Run FTS Search
    from backend.utils.search_db import search_sqlite_fts, search_vector
    fts_results = search_sqlite_fts(expanded_queries, limit=50, video_ids=video_ids if video_ids else None)

    # Run Vector Search if Gemini API key and remote Turso are active
    vector_results = []
    db_url = os.environ.get("TURSO_DATABASE_URL")
    if gemini_key and db_url and "turso.io" in db_url:
        try:
            from backend.utils.youtube import generate_embeddings_gemini
            query_embs = generate_embeddings_gemini([query], gemini_key)
            if query_embs:
                vector_results = search_vector(query_embs[0], limit=50, video_ids=video_ids if video_ids else None)
        except Exception as ve:
            logger.error(f"Vector search failed: {ve}")

    # Merge results (Hybrid Search)
    merged = {}
    
    def add_to_merged(source_results, search_type):
        for item in source_results:
            vid = item["video_id"]
            if vid not in merged:
                merged[vid] = {
                    "video_id": vid,
                    "max_score": item["max_score"],
                    "matches": []
                }
            else:
                merged[vid]["max_score"] = max(merged[vid]["max_score"], item["max_score"])
                
            existing_starts = {round(m["start"], 1) for m in merged[vid]["matches"]}
            for match in item["matches"]:
                rounded_start = round(match["start"], 1)
                if rounded_start not in existing_starts:
                    existing_starts.add(rounded_start)
                    if "match_type" not in match:
                        match["match_type"] = search_type
                    merged[vid]["matches"].append(match)

    add_to_merged(fts_results, "fts")
    add_to_merged(vector_results, "semantic")
    
    results = list(merged.values())
    results.sort(key=lambda x: x["max_score"], reverse=True)

    for r in results:
        r["thumbnail"] = f"https://img.youtube.com/vi/{r['video_id']}/mqdefault.jpg"
        r["best_score"] = r["max_score"]

    logger.info(f"Search complete: '{query}' — {len(results)} videos returned.")
    return jsonify({
        "query": query,
        "expanded_queries": expanded_queries,
        "results": results
    }), 200


@app.route("/api/summarize-video", methods=["POST"])
@limiter.limit("10 per minute")
def summarize_video():
    """
    Summarize a video transcript using AI into 3 bullet points.
    """
    data = request.get_json() or {}
    video_id = sanitize_input(data.get("video_id", ""))
    
    if not video_id:
        raise ValueError("video_id parameter is required")
        
    try:
        # Fetch transcript
        transcript = youtube_client.fetch_video_transcript(video_id)
        if not transcript:
            return jsonify({"error": "No transcript available for this video."}), 404
            
        full_text = " ".join([line.get("text", "") for line in transcript])
        
        # Safe limit to keep within prompt sizes
        if len(full_text) > 40000:
            full_text = full_text[:40000] + "... (เนื้อหามีการตัดทอนเพื่อการสรุป)"
            
        prompt = [
            {
                "role": "system", 
                "content": "คุณคือผู้เชี่ยวชาญด้านอิสลามศึกษาและ AI อัจฉริยะ ทำหน้าที่สรุปเนื้อหาจากซับไตเติ้ลวิดีโอการบรรยายศาสนาเป็นภาษาไทยแบบกระชับ 3 หัวข้อหลัก (Bullet points) เท่านั้น แต่ละหัวข้อย่อยควรครอบคลุมใจความสำคัญ ลึกซึ้ง และตรงตามหลักการศาสนา ใช้ภาษาที่เข้าใจง่ายและสละสลวย และจัดรูปแบบแบบมีหัวข้อย่อยด้วยไอคอนสวยงาม"
            },
            {
                "role": "user", 
                "content": f"กรุณาสรุปเนื้อหาวิดีโอนี้จากซับไตเติ้ลบรรยาย:\n\n{full_text}"
            }
        ]
        
        from backend.utils.llm import generate_completion
        summary = generate_completion(prompt, model="google/gemini-2.0-flash-exp:free", temperature=0.3)
        return jsonify({
            "video_id": video_id,
            "summary": summary
        }), 200
    except Exception as e:
        logger.error(f"Error summarizing video {video_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/bulk-index", methods=["POST"])
def bulk_index():
    """
    Pre-indexes transcripts for a list of video IDs into Firebase/local cache.
    ใช้สำหรับ batch ดึง transcript ล่วงหน้า ก่อนที่ผู้ใช้จะค้นหา
    เพื่อให้การค้นหาในอนาคตครอบคลุมทุกคลิปและเร็วขึ้น
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {Config.ADMIN_SECRET}":
        return jsonify({"error": "Unauthorized. Invalid Admin Token."}), 401

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


@app.route("/api/bulk-sync-cc", methods=["POST"])
def bulk_sync_cc():
    """
    Fast sync of native YouTube CCs. Skips videos that already exist in DB.
    Uses youtube-transcript-api and bulk Turso inserts.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {Config.ADMIN_SECRET}":
        return jsonify({"error": "Unauthorized. Invalid Admin Token."}), 401

    data = request.get_json() or {}
    video_ids = data.get("video_ids", [])
    
    if not video_ids:
        return jsonify({"error": "video_ids is required"}), 400
        
    try:
        from backend.utils.search_db import get_db_stats
        from backend.utils.youtube import YouTubeTranscriptApi, save_transcript_to_sqlite
        
        # Get existing transcribed IDs to skip
        stats = get_db_stats()
        existing_ids = set(stats.get("transcribed_ids", []))
        
        success = 0
        failed = 0
        skipped = 0
        
        # Limit to 8 per request to prevent Vercel 10s timeout
        video_ids = video_ids[:8] 
        
        for vid in video_ids:
            if vid in existing_ids:
                skipped += 1
                continue
                
            try:
                raw_transcript = YouTubeTranscriptApi.get_transcript(vid, languages=['th'])
                # Format to our schema
                transcript = youtube_client._format_transcript(raw_transcript)
                # Save to Turso using Batch write
                save_transcript_to_sqlite(vid, transcript)
                success += 1
            except Exception as e:
                logger.info(f"CC Sync failed for {vid} (Maybe no CC): {str(e)}")
                failed += 1
                
        return jsonify({
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "processed": len(video_ids)
        }), 200
    except Exception as e:
        logger.error(f"Bulk CC Sync error: {str(e)}")
        return jsonify({"error": str(e)}), 500

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

        # Start of streaming response
        from flask import Response, stream_with_context
        import json
        
        def generate():
            from backend.utils.llm import generate_completion
            from backend.utils.search_db import search_sqlite_fts, fetch_batch_surrounding_context
            
            try:
                # Step 1: Extract keywords
                yield f"data: {json.dumps({'type': 'status', 'message': 'กำลังวิเคราะห์คำถาม...'}, ensure_ascii=False)}\n\n"
                
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
                    
                stopwords = ["คือ", "อะไร", "ไหม", "ครับ", "ค่ะ", "ช่วยบอก", "หน่อย", "อยากรู้", "เรื่อง", "ว่า", "ยังไง", "บ้าง", "ทำไม", "?", "ในคลิป", "อาจารย์"]
                for word in stopwords:
                    keywords = keywords.replace(word, " ")
                keywords = " ".join(keywords.split())
                
                # Step 2: Search transcripts (Hybrid)
                yield f"data: {json.dumps({'type': 'status', 'message': f'กำลังวิเคราะห์ความหมายและค้นหา...'}, ensure_ascii=False)}\n\n"
                logger.info(f"RAG searching for keywords: {keywords}")
                
                # 1. FTS Search
                fts_results = search_sqlite_fts(keywords, limit=5)
                if not fts_results:
                    words = [w for w in keywords.split() if len(w) > 1]
                    if words:
                        fts_results = search_sqlite_fts(words, limit=5)
                
                # 2. Vector Search (Semantic) using full user message
                vector_results = []
                gemini_key = Config.GEMINI_API_KEY
                db_url = os.environ.get("TURSO_DATABASE_URL")
                if gemini_key and db_url and "turso.io" in db_url:
                    try:
                        from backend.utils.youtube import generate_embeddings_gemini
                        from backend.utils.search_db import search_vector
                        query_embs = generate_embeddings_gemini([last_message], gemini_key)
                        if query_embs:
                            vector_results = search_vector(query_embs[0], limit=5)
                    except Exception as ve:
                        logger.error(f"Vector search in chat failed: {ve}")
                
                # Merge FTS and Vector (Hybrid)
                merged_dict = {}
                def add_to_merged(source_results):
                    for item in source_results:
                        vid = item["video_id"]
                        if vid not in merged_dict:
                            merged_dict[vid] = item
                        else:
                            merged_dict[vid]["matches"].extend(item["matches"])
                            merged_dict[vid]["max_score"] = max(merged_dict[vid]["max_score"], item["max_score"])
                
                add_to_merged(fts_results)
                add_to_merged(vector_results)
                
                combined_results = list(merged_dict.values())
                combined_results.sort(key=lambda x: x["max_score"], reverse=True)
                top_matches = combined_results[:5]
                context_text = ""
                
                if top_matches:
                    yield f"data: {json.dumps({'type': 'status', 'message': 'กำลังอ่านซับไตเติ้ลจากคลิปที่เกี่ยวข้อง...'}, ensure_ascii=False)}\n\n"
                    context_items = []
                    for r in top_matches:
                        vid = r["video_id"]
                        for m in r["matches"][:2]:
                            context_items.append({"video_id": vid, "start": m["start"], "text": m["text"]})
                    
                    context_map = fetch_batch_surrounding_context(context_items, window_seconds=30)
                    
                    # Map video titles from frontend payload
                    video_list = data.get("videos", [])
                    video_title_map = {v.get("id"): v.get("title") for v in video_list}
                    
                    context_text = "อ้างอิงจากข้อมูลซับไตเติ้ลในฐานข้อมูล:\n"
                    for r in top_matches:
                        vid = r["video_id"]
                        title = video_title_map.get(vid) or r.get("title") or f"วิดีโอ {vid}"
                        for m in r["matches"][:2]:
                            merged_text = context_map.get((vid, m["start"]), m["text"])
                            context_text += f"- ชื่อคลิป: \"{title}\" (นาทีที่ {m['timestamp']}): \"{merged_text}\"\n"
                else:
                    context_text = "ไม่มีข้อมูลในฐานข้อมูลที่ตรงกับคำถามนี้"
        
                # Step 3: Build the final prompt and call the LLM
                yield f"data: {json.dumps({'type': 'status', 'message': 'กำลังเรียบเรียงคำตอบ...'}, ensure_ascii=False)}\n\n"
                system_prompt = f"""คุณคือ 'ผู้ช่วย AI อัจฉริยะด้านอิสลามศึกษา' ที่มีความฉลาดระดับโลก เป็นมิตร คุยเก่ง และมีความรู้ลึกซึ้ง 
บุคลิกของคุณคือ: อบอุ่น เป็นธรรมชาติ ฉลาดหลักแหลม อธิบายเรื่องยากให้เห็นภาพง่ายๆ เหมือนเพื่อนที่รอบรู้หรือพี่ชายที่กำลังให้คำปรึกษา (สามารถใช้อีโมจิ 🌟💡✨ ได้ตามความเหมาะสมเพื่อให้ดูเป็นมนุษย์)

ข้อมูลจากคลังสมอง (วิดีโอของอาจารย์) ที่ค้นพบสำหรับคำถามนี้:
{context_text}

=== กฎเหล็กในการทำงานของคุณ ===
1. **การผสมผสานข้อมูล (RAG)**: 
   - หากใน 'คลังสมอง' มีเนื้อหาที่ตรงกับคำถาม ให้อธิบายเนื้อหานั้นออกมาอย่างลื่นไหล และต้องให้เครดิตเสมอแบบเนียนๆ เช่น "เรื่องนี้มีคำตอบชัดเจนเลยครับ ในคลิปที่ชื่อว่า [ชื่อคลิป] ช่วงนาทีที่ X:XX อาจารย์ได้อธิบายไว้ว่า..."
   - **ห้ามพิมพ์รหัสวิดีโอ (Video ID) ออกมาเด็ดขาด!** ให้เรียกชื่อคลิปตรงๆ ให้มนุษย์อ่านเข้าใจง่าย

2. **เมื่อคลังสมองไม่มีข้อมูล**:
   - ห้ามตอบทื่อๆ ว่า "ไม่พบข้อมูล" เด็ดขาด! 
   - ให้คุณดึง 'ความรู้อันมหาศาลในตัวคุณเอง' ออกมาตอบอย่างละเอียดและฉลาดที่สุด พร้อมอธิบายด้วยความมั่นใจ 
   - จากนั้นค่อยบอกทิ้งท้ายแบบเนียนๆ ว่า "(ปล. ตอนนี้ผมยังหาคลิปของอาจารย์ที่พูดเรื่องนี้แบบเป๊ะๆ ไม่เจอ เลยขออนุญาตใช้ความรู้ส่วนตัวอธิบายให้ฟังก่อนนะครับ 😊)"

3. **เทคนิคการคุยแบบมนุษย์ (Human-like)**:
   - ใช้คำเชื่อมที่ดูเป็นธรรมชาติ (เช่น "อ๋อเข้าใจแล้วครับ", "จริงๆ แล้วเรื่องนี้ลึกซึ้งมากครับ", "เปรียบเทียบง่ายๆ คือ...") 
   - ใช้ภาษาที่สุภาพและลึกซึ้ง แต่ไม่เป็นทางการจนแข็งทื่อ
   - ห้ามใช้ Markdown แบบหัวข้อ (#) หรือตัวหนา (**) ที่ดูเป็นหุ่นยนต์ ให้ใช้วิธีเว้นวรรคและขึ้นบรรทัดใหม่ในการจัดหน้าเว็บให้อ่านง่ายสบายตา

4. **ความถูกต้องทางศาสนา**: 
   - ทุกคำตอบต้องอิงตามหลักการอิสลามที่ถูกต้อง ห้ามแต่งเติมหลักการเองเด็ดขาด
"""
                
                final_messages = [{"role": "system", "content": system_prompt}]
                final_messages.extend(sanitized_messages[-5:])
                
                # First yield the context used so frontend can display it
                yield f"data: {json.dumps({'type': 'context', 'context_used': top_matches, 'keywords_searched': keywords}, ensure_ascii=False)}\n\n"
                
                # Then yield chunks of the answer
                answer_stream = generate_completion(final_messages, temperature=0.7, stream=True)
                for chunk in answer_stream:
                    if chunk:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
                        
            except Exception as e:
                logger.error(f"Stream error: {e}")
                err_data = {"type": "chunk", "content": f"\n\n[ระบบขัดข้อง: เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง: {str(e)}]"}
                yield f"data: {json.dumps(err_data, ensure_ascii=False)}\n\n"
                
            # Finally send done
            yield f"data: [DONE]\n\n"
            
        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    except Exception as e:
        logger.exception("Chat API Error")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
