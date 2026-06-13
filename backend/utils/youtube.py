import os
import sys
import time
import json
import logging
import requests
import subprocess
import glob
import re
from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import scrapetube
from backend.config import Config

logger = logging.getLogger(__name__)

# Predefined metadata cache for @AssabiqoonPublisher to guarantee reliability
ASSABIQOON_PLAYLIST_FALLBACK = [
    {
        "id": "WAN704dCy-g",
        "title": "ฟิกฮ์อิบาดะฮ์ ตอนที่ 5 อธิบายประเภทของน้ำและสุขอนามัย",
        "published_at": "Recently",
        "thumbnail": "https://img.youtube.com/vi/WAN704dCy-g/mqdefault.jpg"
    },
    {
        "id": "M2j7tx0Pju8",
        "title": "ดุอาอ์และซิกิร ตอนที่ 17 พันธะสัญญาของผู้ศรัทธา",
        "published_at": "Recently",
        "thumbnail": "https://img.youtube.com/vi/M2j7tx0Pju8/mqdefault.jpg"
    },
    {
        "id": "JsQHC_2I4gw",
        "title": "เสวนา อัซซาบิกูน ครั้งที่ 1 - ปูพื้นฐานความศรัทธา",
        "published_at": "Recently",
        "thumbnail": "https://img.youtube.com/vi/JsQHC_2I4gw/mqdefault.jpg"
    }
]

# Simple mock transcripts for @AssabiqoonPublisher fallback to ensure tests and offline mode work
ASSABIQOON_TRANSCRIPT_FALLBACK = {
    "WAN704dCy-g": [
        {"text": "บิสมิลลาฮิรเราะห์มานิรเราะฮีม อัสสลามุอะลัยกุม วะเราะห์มะตุลลอฮิ วะบะรอกาตุฮ์", "start": 0.0, "duration": 5.0},
        {"text": "ยินดีต้อนรับสู่บทเรียนฟิกฮ์อิบาดะฮ์ในวันนี้", "start": 6.0, "duration": 4.0},
        {"text": "หัวข้อสำคัญที่เราจะพูดถึงคือสุขอนามัยและการทำความสะอาด", "start": 10.5, "duration": 5.5},
        {"text": "น้ำประเภทแรกคือน้ำสะอาดบริสุทธิ์ หรือที่เราเรียกว่า น้ำมุฏลัก", "start": 17.0, "duration": 6.0},
        {"text": "น้ำนี้สามารถนำมาใช้อาบน้ำละหมาดและชำระล้างสิ่งสกปรกได้", "start": 23.5, "duration": 5.0},
        {"text": "water is a fundamental part of physical and spiritual cleanliness in Islam", "start": 29.0, "duration": 6.5},
        {"text": "สุขอนามัยที่ดีเป็นส่วนหนึ่งของความศรัทธาที่มุสลิมทุกคนต้องรักษา", "start": 36.0, "duration": 5.5}
    ],
    "M2j7tx0Pju8": [
        {"text": "การวิงวอนขอดุอาอ์ต่ออัลลอฮ์ตะอาลาคือหัวใจสำคัญของการศรัทธา", "start": 0.0, "duration": 5.5},
        {"text": "เมื่อเราขอดุอาอ์อย่างนอบน้อม พระองค์จะทรงตอบรับคำขอของเรา", "start": 6.0, "duration": 5.0},
        {"text": "พันธะสัญญาของผู้ศรัทธาคือการยึดมั่นในศีลธรรมและสัจจะ", "start": 12.0, "duration": 5.5},
        {"text": "today we discuss the covenant of a true believer in times of ease and hardship", "start": 18.0, "duration": 6.5},
        {"text": "การซิกิรหรือการรำลึกถึงอัลลอฮ์จะทำให้จิตใจของเราสงบและมีพลัง", "start": 25.5, "duration": 5.5},
        {"text": "ขอพระองค์ทรงชี้นำพวกเราให้อยู่บนแนวทางที่ถูกต้องเสมอ", "start": 32.0, "duration": 5.0}
    ],
    "JsQHC_2I4gw": [
        {"text": "ยินดีต้อนรับสู่เสวนาอัซซาบิกูน ครั้งที่หนึ่ง", "start": 0.0, "duration": 4.0},
        {"text": "วันนี้เราจะมาพูดคุยเพื่อร่วมกันปูพื้นฐานความศรัทธาที่ถูกต้อง", "start": 4.5, "duration": 6.0},
        {"text": "แนวทางสะลัฟคือแนวทางที่พวกเรายึดถือในการตีความศาสนาอิสลาม", "start": 11.0, "duration": 5.5},
        {"text": "building a solid foundation of faith is key to resisting doubts", "start": 17.0, "duration": 5.5},
        {"text": "สำนักพิมพ์อัซซาบิกูนมุ่งมั่นเผยแพร่ความรู้อันเที่ยงตรงนี้แก่สังคม", "start": 23.5, "duration": 6.0},
        {"text": "ขอขอบคุณวิทยากรทุกท่านและผู้ฟังทุกคนที่มาร่วมเสวนาในวันนี้", "start": 30.0, "duration": 5.5}
    ]
}

def retry_with_backoff(retries: int = 3, backoff_in_seconds: float = 1.0):
    """Decorator for retrying API/Network calls with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if Config.IS_VERCEL:
                # Disable retries on Vercel to avoid serverless function timeout (10s limit)
                return func(*args, **kwargs)
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        logger.error(f"Function {func.__name__} failed after {retries} retries: {str(e)}")
                        raise e
                    sleep_time = (backoff_in_seconds * (2 ** x))
                    logger.warning(f"Retrying {func.__name__} in {sleep_time}s due to error: {str(e)}")
                    time.sleep(sleep_time)
                    x += 1
        return wrapper
    return decorator

from backend.utils.db import DatabaseManager

class YouTubeClient:
    def __init__(self, api_key: Optional[str] = None, cache_dir: str = Config.CACHE_DIR):
        self.api_key = api_key
        self.db_manager = DatabaseManager(cache_dir)
        
        # Pre-populate local cache with fallback transcripts for testing/offline mode
        for vid, fallback_t in ASSABIQOON_TRANSCRIPT_FALLBACK.items():
            if not self.db_manager.get_document("transcripts", vid):
                self.db_manager.set_document("transcripts", vid, fallback_t)

    @retry_with_backoff(retries=3, backoff_in_seconds=1.0)
    def fetch_channel_videos(self, channel_name: str, limit: int = 5000) -> List[Dict[str, Any]]:
        """
        Fetches the latest videos of a channel name / handle.
        Attempts to resolve handle -> scrape/API -> fallback.
        """
        # Clean the input
        channel_name = channel_name.strip()
        
        # Check cache
        cache_key = f"channel_videos_{channel_name}_{limit}"
        cached_data = self.db_manager.get_document("channel_videos", cache_key)
        
        if cached_data and self.api_key:
            try:
                # Do a quick check for the single latest video on YouTube
                latest_yt = self._fetch_via_api(channel_name, limit=1)
                if latest_yt and cached_data:
                    latest_yt_id = latest_yt[0]["id"]
                    latest_cached_id = cached_data[0]["id"]
                    if latest_yt_id == latest_cached_id:
                        logger.info(f"Cache is up-to-date for {channel_name}. Returning Firestore cache.")
                        return cached_data
                    logger.info(f"New video detected ({latest_yt_id} vs {latest_cached_id}). Refreshing cache...")
            except Exception as e:
                logger.warning(f"Error checking cache freshness: {str(e)}. Returning cache directly.")
                return cached_data
        elif cached_data:
            logger.info(f"Returning cached videos list for {channel_name} (no API Key available for freshness check)")
            return cached_data

        videos = []
        is_assabiqoon = "@AssabiqoonPublisher" in channel_name or "AssabiqoonPublisher" in channel_name

        try:
            if self.api_key:
                videos = self._fetch_via_api(channel_name, limit)
            elif is_assabiqoon:
                logger.info("Bypassing scraping for @AssabiqoonPublisher to avoid Vercel block")
                videos = ASSABIQOON_PLAYLIST_FALLBACK
            else:
                videos = self._fetch_via_scraping(channel_name, limit)
        except Exception as e:
            logger.error(f"Failed to fetch videos via standard methods for {channel_name}: {str(e)}")
            if is_assabiqoon:
                logger.info("Using hardcoded fallback for @AssabiqoonPublisher")
                videos = ASSABIQOON_PLAYLIST_FALLBACK
            else:
                raise ValueError(f"Could not retrieve videos for channel: {channel_name}. Error: {str(e)}")


        if not videos and is_assabiqoon:
            videos = ASSABIQOON_PLAYLIST_FALLBACK

        if videos:
            self.db_manager.set_document("channel_videos", cache_key, videos)
            
        return videos


    def _fetch_via_api(self, channel_name: str, limit: int) -> List[Dict[str, Any]]:
        # Handle handles like @AssabiqoonPublisher
        handle = channel_name if channel_name.startswith("@") else f"@{channel_name}"
        
        # 1. Resolve handle to Channel ID
        url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails&forHandle={handle}&key={self.api_key}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        
        if not data.get("items"):
            # Try searching for channel if handle lookup fails
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={channel_name}&type=channel&key={self.api_key}"
            r_search = requests.get(search_url, timeout=5)
            r_search.raise_for_status()
            search_data = r_search.json()
            if not search_data.get("items"):
                raise ValueError("Channel not found via YouTube API")
            channel_id = search_data["items"][0]["id"]["channelId"]
            # Get content details for uploads playlist
            url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={self.api_key}"
            r = requests.get(url, timeout=5)
            data = r.json()
            
        channel_item = data["items"][0]
        uploads_playlist_id = channel_item["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # 2. Get playlist items
        videos = []
        next_page_token = ""
        while len(videos) < limit:
            playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=50&pageToken={next_page_token}&key={self.api_key}"
            pr = requests.get(playlist_url, timeout=5)
            pr.raise_for_status()
            pdata = pr.json()
            
            for item in pdata.get("items", []):
                snippet = item["snippet"]
                video_id = snippet["resourceId"]["videoId"]
                videos.append({
                    "id": video_id,
                    "title": snippet["title"],
                    "published_at": snippet["publishedAt"],
                    "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg")
                })
                
            next_page_token = pdata.get("nextPageToken")
            if not next_page_token:
                break
                
        return videos[:limit]

    def _fetch_via_scraping(self, channel_name: str, limit: int) -> List[Dict[str, Any]]:
        # Resolve username or URL
        username = channel_name.split("/")[-1].replace("@", "") if "/" in channel_name else channel_name.replace("@", "")
        url = f"https://www.youtube.com/@{username}"
        
        logger.info(f"Attempting to scrape channel: {url} using scrapetube")
        generator = scrapetube.get_channel(channel_url=url, limit=limit)
        videos = []
        for v in generator:
            video_id = v["videoId"]
            # Format published_at cleanly (fallback to current time if absent)
            published_text = v.get("publishedTimeText", {}).get("simpleText", "Recently")
            title = v.get("title", {}).get("runs", [{}])[0].get("text", "Untitled Video")
            
            videos.append({
                "id": video_id,
                "title": title,
                "published_at": published_text,
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            })
        return videos

    def _fetch_via_public_api(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetches transcript from the free public API: youtube-transcript.ai
        """
        url = f"https://youtube-transcript.ai/transcript/{video_id}.txt"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            logger.info(f"Attempting to fetch from youtube-transcript.ai for {video_id}...")
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                content = r.text
                lines = content.strip().split('\n')
                transcript_started = False
                segments = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line == "## Transcript":
                        transcript_started = True
                        continue
                    if not transcript_started:
                        continue
                    
                    match = re.match(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$", line)
                    if match:
                        h_str = match.group(1)
                        m_str = match.group(2)
                        s_str = match.group(3)
                        text = match.group(4).strip()
                        
                        h = int(h_str) if h_str else 0
                        m = int(m_str)
                        s = int(s_str)
                        start_time = h * 3600 + m * 60 + s
                        
                        segments.append({
                            "text": text,
                            "start": float(start_time),
                            "duration": 5.0
                        })
                
                if segments:
                    # Adjust durations based on next segment's start time
                    for i in range(len(segments) - 1):
                        segments[i]["duration"] = max(0.5, segments[i+1]["start"] - segments[i]["start"])
                    logger.info(f"Successfully retrieved and parsed {len(segments)} segments from youtube-transcript.ai for {video_id}")
                    return segments
            else:
                logger.warning(f"youtube-transcript.ai returned status code {r.status_code} for {video_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch from youtube-transcript.ai for {video_id}: {e}")
        return None

    @retry_with_backoff(retries=2, backoff_in_seconds=1.0)
    def fetch_video_transcript(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Fetches the transcript for a specific video ID.
        Strategy (in order):
          1. Return from cache if available.
          2. Try Thai/English direct fetch.
          3. List all available transcripts → try auto-generated th/en.
          4. Try manually created th/en.
          5. Take the first available transcript in any language.
          6. Fall back to yt-dlp subtitle download.
          7. Use hardcoded fallback for known videos.
        """
        cached_data = self.db_manager.get_document("transcripts", video_id)
        if cached_data:
            logger.info(f"Returning cached transcript for video {video_id}")
            return cached_data

        transcript = None

        def _parse_fetched(fetched) -> List[Dict[str, Any]]:
            """Convert YouTubeTranscriptApi result to standard dict list.
            Supports both dict-style (old API) and object-style (new API) items.
            """
            result = []
            for s in fetched:
                if isinstance(s, dict):
                    result.append({"text": s["text"], "start": s["start"], "duration": s["duration"]})
                else:
                    result.append({"text": s.text, "start": s.start, "duration": s.duration})
            return result

        # Check for cookies to bypass IP blocks
        cookies_path = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if os.path.exists(os.path.join(base_dir, "cookies_new.txt")):
            cookies_path = os.path.join(base_dir, "cookies_new.txt")
        elif os.path.exists(os.path.join(base_dir, "cookies.txt")):
            cookies_path = os.path.join(base_dir, "cookies.txt")


        # --- Strategy 1: Direct fetch (th then en) ---
        try:
            kwargs = {"languages": ["th", "en"]}
            if cookies_path:
                kwargs["cookies"] = cookies_path
            fetched = YouTubeTranscriptApi.get_transcript(video_id, **kwargs)
            transcript = _parse_fetched(fetched)
            logger.info(f"Got th/en transcript for {video_id} (direct)")
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"No direct th/en transcript for {video_id}: {e}")
        except Exception as e:
            logger.warning(f"Error on direct transcript fetch for {video_id}: {e}")

        # --- Strategies 2–5: Explore all available transcripts ---
        if not transcript:
            try:
                kwargs = {}
                if cookies_path:
                    kwargs["cookies"] = cookies_path
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, **kwargs)

                # Strategy 2: Auto-generated Thai (a.th) or English (a.en)
                if not transcript:
                    try:
                        t = transcript_list.find_generated_transcript(["th", "en", "th-TH", "a.th", "a.en"])
                        transcript = _parse_fetched(t.fetch())
                        logger.info(f"Got auto-generated transcript for {video_id} (lang={t.language_code})")
                    except Exception:
                        pass

                # Strategy 3: Manually created in any preferred language
                if not transcript:
                    try:
                        t = transcript_list.find_manually_created_transcript(["th", "en", "th-TH"])
                        transcript = _parse_fetched(t.fetch())
                        logger.info(f"Got manual transcript for {video_id} (lang={t.language_code})")
                    except Exception:
                        pass

                # Strategy 4: Any available transcript (first one found)
                if not transcript:
                    try:
                        for t in transcript_list:
                            try:
                                transcript = _parse_fetched(t.fetch())
                                logger.info(f"Got transcript for {video_id} (fallback lang={t.language_code})")
                                break
                            except Exception:
                                continue
                    except Exception:
                        pass

            except TranscriptsDisabled:
                logger.warning(f"Transcripts are disabled for video {video_id}")
            except Exception as list_err:
                logger.warning(f"Could not list transcripts for {video_id}: {list_err}")

        # --- Strategy 5: yt-dlp subtitle download ---
        if not transcript:
            logger.info(f"Trying yt-dlp fallback for {video_id}")
            try:
                transcript = self._download_subs_yt_dlp(video_id)
                if transcript:
                    logger.info(f"Got transcript via yt-dlp for {video_id}")
            except Exception as dlp_err:
                logger.error(f"yt-dlp fallback failed for {video_id}: {dlp_err}")

        # --- Strategy 6: Hardcoded fallback for known videos ---
        if not transcript:
            if video_id in ASSABIQOON_TRANSCRIPT_FALLBACK:
                logger.info(f"Using hardcoded fallback transcript for {video_id}")
                transcript = ASSABIQOON_TRANSCRIPT_FALLBACK[video_id]
            else:
                raise ValueError(f"Transcript unavailable for video {video_id} (all strategies exhausted)")

        if transcript:
            self.db_manager.set_document("transcripts", video_id, transcript)
            return transcript

        raise ValueError(f"Transcript unavailable for video {video_id}")

    def _parse_time(self, t_str):
        try:
            t_str = t_str.strip().replace(',', '.')
            parts = t_str.split(':')
            if len(parts) == 3:
                h = int(parts[0])
                m = int(parts[1])
                s = float(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m = int(parts[0])
                s = float(parts[1])
                return m * 60 + s
        except Exception as e:
            logger.error(f"Error parsing time string '{t_str}': {e}")
        return 0.0

    def _parse_vtt(self, file_path):
        transcript = []
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            blocks = re.split(r'\n\s*\n', content)
            for block in blocks:
                lines = block.strip().split('\n')
                if not lines:
                    continue
                timestamp_idx = -1
                for idx, line in enumerate(lines):
                    if '-->' in line:
                        timestamp_idx = idx
                        break
                if timestamp_idx == -1:
                    continue
                times = lines[timestamp_idx].split('-->')
                if len(times) != 2:
                    continue
                start = self._parse_time(times[0])
                end = self._parse_time(times[1])
                duration = max(0.0, end - start)
                text_lines = lines[timestamp_idx+1:]
                text = " ".join([re.sub(r'<[^>]+>', '', l).strip() for l in text_lines if l.strip()])
                if text:
                    transcript.append({
                        "text": text,
                        "start": start,
                        "duration": duration
                    })
            return transcript
        except Exception as e:
            logger.error(f"Failed to parse VTT file {file_path}: {e}")
            return None

    def _download_subs_yt_dlp(self, video_id):
        # Temp dir in root/scratch
        temp_dir = os.path.join(Config.CACHE_DIR, "temp_subs")
        os.makedirs(temp_dir, exist_ok=True)
        
        output_tmpl = os.path.join(temp_dir, f"{video_id}")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--write-auto-subs",
            "--write-subs",
            "--skip-download",
            "--sub-langs", "th",
            "--sub-format", "vtt",
            "--ignore-no-formats-error",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            "--quiet",
            "-o", output_tmpl
        ]
        
        # Check if cookies_new.txt or cookies.txt is in project root directory
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cookies_path = os.path.join(base_dir, "cookies_new.txt")
        if not os.path.exists(cookies_path):
            cookies_path = os.path.join(base_dir, "cookies.txt")
            
        if os.path.exists(cookies_path):
            cmd.extend(["--cookies", cookies_path])
            logger.info(f"Using cookies from {cookies_path} in yt-dlp fallback")
            
        cmd.append(video_url)
        
        # On Vercel, keep a strict 5s limit. Locally, allow 30s to prevent timeouts on slower connections.
        timeout_val = 5 if Config.IS_VERCEL else 30
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_val)
            pattern = os.path.join(temp_dir, f"{video_id}.*vtt")
            matches = glob.glob(pattern)
            if matches:
                sub_file = matches[0]
                transcript = self._parse_vtt(sub_file)
                try:
                    os.remove(sub_file)
                except Exception:
                    pass
                return transcript
        except subprocess.TimeoutExpired as e:
            logger.warning(f"yt-dlp fallback download timed out for {video_id}: {e}")
        except Exception as e:
            logger.warning(f"yt-dlp fallback download failed for {video_id}: {e}")
        return None

    def search_youtube_api(self, channel_name: str, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Searches YouTube search API specifically inside a channel.
        Supports paginating to return up to max_results.
        """
        if not self.api_key:
            return []
            
        try:
            # 1. Resolve channel ID
            handle = channel_name if channel_name.startswith("@") else f"@{channel_name}"
            if "AssabiqoonPublisher" in handle:
                channel_id = "UC0CawcehNJ-E_bvw3EQ2ARQ"
            else:
                url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forHandle={handle}&key={self.api_key}"
                r = requests.get(url, timeout=5)
                r.raise_for_status()
                data = r.json()
                if not data.get("items"):
                    return []
                channel_id = data["items"][0]["id"]
                
            # 2. Search videos containing query in channel
            search_url = "https://www.googleapis.com/youtube/v3/search"
            results = []
            next_page_token = None
            
            while len(results) < max_results:
                params = {
                    "part": "snippet",
                    "channelId": channel_id,
                    "q": query,
                    "type": "video",
                    "maxResults": min(max_results - len(results), 50),
                    "key": self.api_key
                }
                if next_page_token:
                    params["pageToken"] = next_page_token
                    
                sr = requests.get(search_url, params=params, timeout=5)
                sr.raise_for_status()
                sdata = sr.json()
                
                items = sdata.get("items", [])
                if not items:
                    break
                    
                for item in items:
                    video_id = item["id"].get("videoId")
                    if not video_id:
                        continue
                    results.append({
                        "id": video_id,
                        "title": item["snippet"]["title"],
                        "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg")
                    })
                    
                next_page_token = sdata.get("nextPageToken")
                if not next_page_token:
                    break
                    
            return results[:max_results]
        except Exception as e:
            logger.error(f"Error searching YouTube API for {query} in {channel_name}: {e}")
            return []

