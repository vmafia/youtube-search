import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "prod-secret-key-12345")
    DEBUG = os.environ.get("FLASK_ENV") == "development"
    
    # YouTube API
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
    
    # Cache and limits
    CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Log path
    LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "app.log")
    
    # Limit settings
    RATELIMIT_DEFAULT = "30 per minute"
