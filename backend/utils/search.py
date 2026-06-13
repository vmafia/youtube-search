import re
import os
import requests
import json
import logging
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

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
    
    # Strip Arabic diacritics (Tashkeel)
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    
    # Normalize Arabic variations
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه")
    text = text.replace("ى", "ي")
    # Strip Kashida/Tatweel
    text = text.replace("ـ", "")

    # Keep Thai characters, English letters, numbers, and Arabic characters
    text = re.sub(r"[^\u0e00-\u0e7fa-zA-Z0-9\u0600-\u06ff\s]", "", text)    
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()

ISLAMIC_SYNONYMS = {
    "น้ำละหมาด": ["น้ำละหมาด", "อาบน้ำละหมาด", "วุฎูอ์", "วุฏู", "wudu", "wudhu"],
    "ละหมาด": ["ละหมาด", "ซอลาต", "ศอลาต", "นมาซ", "solah", "namaz"],
    "อิบาดะฮ์": ["อิบาดะฮ์", "อิบาดะห์", "อิบาดะฮฺ", "อิบาดะ", "ibadah", "worship"],
    "อัลลอฮ์": ["อัลลอฮ์", "อัลลอฮฺ", "อัลเลาะฮ์", "อัลเลาะฮฺ", "allah"],
    "ดุอาอ์": ["ดุอาอ์", "ดุอา", "ดุอาอฺ", "ดุอาห์", "duas", "dua"],
    "ซิกิร": ["ซิกิร", "ซิกรุลลอฮ์", "ซิเกร", "ซิกิรฺ", "dhikr", "zikr"],
    "ซุนนะฮ์": ["ซุนนะฮ์", "ซุนนะห์", "ซุนนะฮฺ", "สุนนะฮ์", "สุนัต", "sunnah"],
    "หะดีษ": ["หะดีษ", "ฮะดีษ", "ฮะดีส", "หะดีส", "hadith"],
    "สะลัฟ": ["สะลัฟ", "สลัฟ", "สะลัฟศอลิห์", "salaf"],
    "อุลามาอ์": ["อุลามาอ์", "อุลามา", "อูลามะ", "อุลามาอฺ", "scholars", "ulama"],
    "มุฮัมมัด": ["มุฮัมมัด", "โมฮัมหมัด", "มูฮัมหมัด", "muhammad"],
    "สวรรค์": ["สวรรค์", "ญันนะฮ์", "ญันนะห์", "ญันนะฮฺ", "jannah"],
    "นรก": ["นรก", "ญะฮันนัม", "ญะฮันนัม", "jahannam"],
}

def get_local_synonyms(query: str) -> List[str]:
    norm_q = normalize_text(query)
    results = {query}
    for key, synonyms in ISLAMIC_SYNONYMS.items():
        if normalize_text(key) in norm_q or norm_q in normalize_text(key):
            results.update(synonyms)
    return list(results)

def expand_query_ai(query: str, api_key: str) -> List[str]:
    if not api_key:
        return [query]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    prompt = f"""You are an Islamic scholar and linguistics expert specializing in Thai and Arabic transcriptions.
Expand the search query "{query}" to capture all common spelling variations, transliterations, synonyms, and related terms used in Thai Islamic lectures.
Return ONLY a JSON list of strings (maximum 8 terms, including the original query). Do not include markdown code block formatting or any text other than the raw JSON.
Example query: "น้ำละหมาด"
Output: ["น้ำละหมาด", "อาบน้ำละหมาด", "วุฎูอ์", "วุฏู", "wudu", "wudhu"]
Example query: "อิบาดะฮ์"
Output: ["อิบาดะฮ์", "อิบาดะห์", "อิบาดะฮฺ", "อิบาดะ", "ibadah", "worship"]"""
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=5)
        if r.status_code == 200:
            res_json = r.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.startswith("```"):
                text = re.sub(r"^```json\s*|```$", "", text, flags=re.MULTILINE)
            terms = json.loads(text)
            if isinstance(terms, list):
                if query not in terms:
                    terms.insert(0, query)
                return [str(t).strip() for t in terms if t]
    except Exception as e:
        logger.error(f"Error expanding query via Gemini: {e}")
    return [query]

def expand_query(query: str, api_key: Optional[str] = None) -> List[str]:
    terms = get_local_synonyms(query)
    if api_key:
        ai_terms = expand_query_ai(query, api_key)
        seen = set()
        merged = []
        for t in terms + ai_terms:
            t_norm = normalize_text(t)
            if t_norm and t_norm not in seen:
                seen.add(t_norm)
                merged.append(t)
        return merged
    return terms

def check_and_convert_milliseconds(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detects if the transcript segment timestamps are in milliseconds and converts them to seconds.
    Also validates None/NaN/Null values to prevent crashes.
    """
    if not transcript:
        return transcript

    is_ms = False
    starts = []
    durations = []
    
    for item in transcript:
        try:
            start_val = item.get("start")
            if start_val is not None:
                starts.append(float(start_val))
        except (ValueError, TypeError):
            pass
        try:
            dur_val = item.get("duration")
            if dur_val is not None:
                durations.append(float(dur_val))
        except (ValueError, TypeError):
            pass

    if starts:
        max_start = max(starts)
        if max_start > 86400:  # More than 24 hours
            is_ms = True
        
    if durations and not is_ms:
        max_duration = max(durations)
        if max_duration > 120:  # Subtitle segment longer than 2 minutes
            is_ms = True

    # Fallback to check if any of the first 10 items have starts > 1000
    if not is_ms and starts:
        for val in starts[:10]:
            if val > 1000:
                is_ms = True
                break

    for item in transcript:
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

        if is_ms:
            start = start / 1000.0
            duration = duration / 1000.0

        item["start"] = round(start, 2)
        item["duration"] = round(duration, 2)

    return transcript

def search_transcript(transcript: List[Dict[str, Any]], query: Any, threshold: float = 80.0) -> List[Dict[str, Any]]:
    """
    Searches the transcript for the given query (string or list of query terms).
    Supports Exact Match, Partial Match, and Fuzzy Match.
    """
    if not query or not transcript:
        return []

    if isinstance(query, str):
        query_terms = [query]
    else:
        query_terms = query

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
        score = 0.0

        for q_term in query_terms:
            norm_query = normalize_text(q_term)
            if not norm_query:
                continue

            # 1. Exact Match / Substring Match (Case-Insensitive normalized)
            if norm_query in norm_text:
                is_match = True
                match_type = "exact" if norm_query == norm_text else "partial"
                score = 100.0
                break
            else:
                # 2. Fuzzy Match using partial ratio
                term_score = fuzz.partial_ratio(norm_query, norm_text)
                if term_score >= threshold:
                    is_match = True
                    match_type = "fuzzy"
                    score = term_score
                    break

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
