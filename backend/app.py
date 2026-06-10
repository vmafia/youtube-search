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
from backend.utils.search import search_transcript

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
        
    results = []
    
    # Hybrid search strategy to prevent timeouts:
    # - If we have a small number of videos, search them directly.
    # - If we have a large number of videos, query YouTube Search API first to find candidates.
    if len(video_ids) <= 10:
        # Direct database search for small list
        for vid in video_ids:
            vid = sanitize_input(vid)
            try:
                transcript = youtube_client.db_manager.get_document("transcripts", vid)
                if not transcript and not Config.IS_VERCEL:
                    try:
                        transcript = youtube_client.fetch_video_transcript(vid)
                    except Exception:
                        pass
                if not transcript:
                    continue
                    
                matches = search_transcript(transcript, query, threshold=threshold)
                if matches:
                    results.append({
                        "video_id": vid,
                        "matches": matches
                    })
            except Exception as e:
                logger.warning(f"Skipping video {vid} during direct search: {str(e)}")
                continue
    else:
        # Candidate search via YouTube Search API for large list (up to 100 candidates)
        channel_name = sanitize_input(data.get("channel_name", "@AssabiqoonPublisher"))
        logger.info(f"Large video list ({len(video_ids)}). Querying YouTube Search API to narrow down candidates.")
        
        matched_videos = youtube_client.search_youtube_api(channel_name, query, max_results=100)
        selected_set = set(video_ids)
        
        for m_vid in matched_videos:
            vid_id = m_vid["id"]
            if vid_id not in selected_set:
                continue
                
            try:
                transcript = youtube_client.db_manager.get_document("transcripts", vid_id)
                # If transcript not found in DB, try fetching on-the-fly if not on Vercel
                if not transcript and not Config.IS_VERCEL:
                    try:
                        transcript = youtube_client.fetch_video_transcript(vid_id)
                    except Exception:
                        pass
                
                if transcript:
                    matches = search_transcript(transcript, query, threshold=threshold)
                    if matches:
                        results.append({
                            "video_id": vid_id,
                            "matches": matches,
                            "title": m_vid["title"],
                            "thumbnail": m_vid["thumbnail"]
                        })
                else:
                    # Transcript is missing. Do not generate fake matches.
                    # Return video metadata and mark transcript as missing.
                    results.append({
                        "video_id": vid_id,
                        "matches": [],
                        "title": m_vid["title"],
                        "thumbnail": m_vid["thumbnail"],
                        "transcript_missing": True
                    })
            except Exception as e:
                logger.warning(f"Error checking candidate video {vid_id}: {str(e)}")
                continue
                
    return jsonify({
        "query": query,
        "results": results
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
