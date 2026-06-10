import re
from typing import List, Dict, Any
from rapidfuzz import fuzz

def normalize_text(text: str) -> str:
    """Normalize text for matching (lowercase, strip special chars, normalize whitespace)."""
    text = text.lower().strip()
    # Keep Thai characters, English letters, and numbers
    text = re.sub(r"[^\u0e00-\u0e7fa-zA-Z0-9\s]", "", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def search_transcript(transcript: List[Dict[str, Any]], query: str, threshold: float = 80.0) -> List[Dict[str, Any]]:
    """
    Searches the transcript for the given query.
    Supports Exact Match, Partial Match, and Fuzzy Match (80%+ similarity).
    Returns list of matches with timestamps.
    """
    if not query or not transcript:
        return []

    norm_query = normalize_text(query)
    if not norm_query:
        return []

    results = []

    # Iterate and search
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
            start_time = float(item.get("start", 0))
            duration = float(item.get("duration", 0))
            results.append({
                "text": original_text,
                "start": round(start_time, 1),
                "end": round(start_time + duration, 1),
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
