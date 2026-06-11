import re
from typing import List, Dict, Any
from rapidfuzz import fuzz

def normalize_text(text: str) -> str:
    """
    Robust Thai/Arabic normalization for phonetic consistency in religious terms.
    Strips tone marks, normalizes consonants and vowels, and prepares text for fuzzy search.
    """
    text = text.lower().strip()
    
    # Strip common Thai tone marks, silent marks, and vocalization aids:
    # ่ (่), ้ (้), ๊ (๊), ๋ (๋), ์ (การันต์), ฺ (พินทุ), ํ (นิคหิต), ๎ (ยามักการ), ็ (ไม้ไต่คู้)
    text = re.sub(r"[\u0e48-\u0e4b\u0e4c\u0e3a\u0e4d\u0e4e\u0e47]", "", text)
    
    # Consolidate homophones/consonants typical in Arabic transcriptions to Thai:
    # ศ, ษ, ซ -> ส
    text = text.replace("ศ", "ส").replace("ษ", "ส").replace("ซ", "ส")
    # ฑ, ฒ, ท, ธ, ถ, ฐ -> ท
    text = text.replace("ฑ", "ท").replace("ฒ", "ท").replace("ธ", "ท").replace("ถ", "ท").replace("ฐ", "ท")
    # ณ -> น
    text = text.replace("ณ", "น")
    # ภ -> พ
    text = text.replace("ภ", "พ")
    # ฬ -> ล
    text = text.replace("ฬ", "ล")
    # ญ -> ย
    text = text.replace("ญ", "ย")
    
    # Consolidate common vowel variations in transcriptions of "Allah" & Arabic particles:
    # เลาะฮ์ / เลาะฮฺ / ลอฮ์ / ลอฮฺ -> ลอ
    text = re.sub(r"เลาะ", "ลอ", text)
    text = re.sub(r"ลอฮ", "ลอ", text)
    text = re.sub(r"ลอห", "ลอ", text)
    
    # Strip any ending 'ห' or 'อ' that represents silent breath at the end of Arabic words
    text = re.sub(r"([ก-ฮ])ห\b", r"\1", text)
    
    # Keep only Thai characters, English letters, and numbers
    text = re.sub(r"[^\u0e00-\u0e7fa-zA-Z0-9\s]", "", text)
    
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def check_and_convert_milliseconds(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detects if the transcript segment timestamps are in milliseconds and converts them to seconds.
    Also validates None/NaN/Null values to prevent crashes.
    """
    if not transcript:
        return transcript

    # Check if first few segments have unusually large starts (highly likely in milliseconds)
    is_ms = False
    for item in transcript[:5]:
        try:
            start = float(item.get("start", 0))
            if start > 1000:
                is_ms = True
                break
        except (ValueError, TypeError):
            continue

    for item in transcript:
        # 1. Convert to float and handle None/NaN
        try:
            start_val = item.get("start")
            start = float(start_val) if start_val is not None else 0.0
            if start != start:  # NaN check
                start = 0.0
        except (ValueError, TypeError):
            start = 0.0

        try:
            dur_val = item.get("duration")
            duration = float(dur_val) if dur_val is not None else 0.0
            if duration != duration:  # NaN check
                duration = 0.0
        except (ValueError, TypeError):
            duration = 0.0

        # 2. Divide by 1000 if milliseconds detected
        if is_ms:
            start = start / 1000.0
            duration = duration / 1000.0

        item["start"] = round(start, 2)
        item["duration"] = round(duration, 2)

    return transcript

def search_transcript(transcript: List[Dict[str, Any]], query: str, threshold: float = 80.0) -> List[Dict[str, Any]]:
    """
    Searches the transcript for the given query.
    Supports Exact Match, Partial Match, and Fuzzy Match.
    """
    if not query or not transcript:
        return []

    norm_query = normalize_text(query)
    if not norm_query:
        return []

    # Ensure transcript timestamps are in seconds and validated
    transcript = check_and_convert_milliseconds(transcript)
    results = []

    for item in transcript:
        original_text = item.get("text", "")
        norm_text = normalize_text(original_text)
        
        if not norm_text:
            continue
            
        is_match = False
        match_type = None
        score = 100.0

        # 1. Exact Match / Substring Match (Case-Insensitive normalized)
        if norm_query in norm_text:
            is_match = True
            match_type = "exact" if norm_query == norm_text else "partial"
        else:
            # 2. Fuzzy Match using partial ratio
            score = fuzz.partial_ratio(norm_query, norm_text)
            if score >= threshold:
                is_match = True
                match_type = "fuzzy"

        if is_match:
            start_time = item["start"]
            duration = item["duration"]
            results.append({
                "text": original_text,
                "start": start_time,
                "end": round(start_time + duration, 2),
                "timestamp": format_timestamp(start_time),
                "score": round(score, 1),
                "match_type": match_type
            })

    return results

def format_timestamp(seconds: float) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    seconds_int = int(round(seconds))
    hours = seconds_int // 3600
    minutes = (seconds_int % 3600) // 60
    secs = seconds_int % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
