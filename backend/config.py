import os
from dotenv import load_dotenv
import secrets
import logging

logger = logging.getLogger(__name__)

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DEBUG = os.environ.get("FLASK_ENV") == "development"
    
    # YouTube API
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    ADMIN_SECRET = os.environ.get("ADMIN_SECRET")
    if not ADMIN_SECRET:
        ADMIN_SECRET = secrets.token_hex(16)
        logger.warning(f"ADMIN_SECRET not set in environment. Generated new random secret: {ADMIN_SECRET}")
    
    # Cache and limits
    IS_VERCEL = os.environ.get("VERCEL") == "1"
    
    if IS_VERCEL:
        CACHE_DIR = "/tmp/cache"
        LOG_DIR = "/tmp/logs"
    else:
        CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))
        LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
        
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "app.log")
    
    # Limit settings
    RATELIMIT_DEFAULT = "30 per minute"

