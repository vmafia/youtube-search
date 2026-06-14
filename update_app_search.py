import os
import re

content = open('backend/app.py', 'r', encoding='utf-8').read()

# Add global transcript cache loader
loader_code = '''
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
'''

if "global_transcripts_cache =" not in content:
    # Insert right before @app.route("/api/search"
    content = content.replace('@app.route("/api/search"', loader_code + '\n@app.route("/api/search"')


# Replace search logic
old_search_logic = '''    # 2. Smart Candidate Gathering:
    # แทนที่จะดึง transcript ทั้ง 3000 คลิป เราจะให้ YouTube Search API ช่วยหาให้
    # โดยส่งคำค้นหา "ทุกคำ" (synonyms) ไปค้นใน YouTube เพื่อกวาดคลิปมาให้ได้มากที่สุด
    candidate_meta = {}  # {video_id: {title, thumbnail}}
    
    if youtube_client.api_key:
        logger.info(f"Gathering candidates using YouTube Search API for {len(expanded_queries)} terms...")
        for term in expanded_queries:
            try:
                # ค้นหาทีละคำ เพื่อให้ครอบคลุมที่สุด
                matched = youtube_client.search_youtube_api(channel_name, term, max_results=50)
                for m in matched:
                    vid = m["id"]
                    if vid in video_ids_set:
                        candidate_meta[vid] = {"title": m["title"], "thumbnail": m["thumbnail"]}
            except Exception as e:
                logger.warning(f"YouTube Search API failed for term '{term}': {str(e)}")
                
        logger.info(f"Found {len(candidate_meta)} unique candidate videos from YouTube Search.")

    # ถ้าหาจาก YouTube API ไม่ได้เลย หรือไม่มี API key ให้ดึงคลิปจาก video_ids มาส่วนหนึ่งแทน
    if not candidate_meta:
        logger.warning("No candidates found via YouTube Search API. Falling back to subset of video_ids.")
        for vid in video_ids[:100]:  # จำกัดแค่ 100 คลิปป้องกัน timeout
            candidate_meta[vid] = {"title": "", "thumbnail": f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"}

    # 3. Fetch Transcripts & Fuzzy Search (ทำเฉพาะ candidate)
    # วิธีนี้จะดึง transcript แค่ ~50-200 คลิป แทนที่จะเป็น 3000 คลิป ทำให้เร็วและไม่โดนแบน
    processed = set()
    for vid, meta in candidate_meta.items():
        if vid in processed:
            continue
        processed.add(vid)

        try:
            transcript = youtube_client.db_manager.get_document("transcripts", vid)

            if not transcript:
                try:
                    transcript = youtube_client.fetch_video_transcript(vid)
                except Exception as fetch_err:
                    logger.warning(f"Could not fetch transcript for candidate {vid}: {fetch_err}")

            if not transcript:
                logger.warning(f"No transcript available for {vid}. Skipping.")
                continue

            matches = search_transcript(transcript, expanded_queries, threshold=threshold)
            if matches:
                result = {
                    "video_id": vid,
                    "matches": matches,
                    "thumbnail": meta["thumbnail"]
                }
                if meta.get("title"):
                    result["title"] = meta["title"]
                results.append(result)

        except Exception as e:
            logger.warning(f"Skipping candidate {vid} during search: {str(e)}")
            continue

    logger.info(f"Search complete: '{query}' — {len(results)} videos matched out of {len(candidate_meta)} candidates.")'''

new_search_logic = '''    # 2. In-Memory Search
    # โหลดไฟล์ all_transcripts ทีเดียว แล้วค้นหาในหน่วยความจำ จะเร็วและหาเจอ 100%
    all_data = load_all_transcripts()
    logger.info(f"Searching across {len(all_data)} transcripts in memory for {len(expanded_queries)} terms...")
    
    for vid, transcript in all_data.items():
        if not video_ids_set or vid in video_ids_set:
            try:
                matches = search_transcript(transcript, expanded_queries, threshold=threshold)
                if matches:
                    results.append({
                        "video_id": vid,
                        "matches": matches,
                        "thumbnail": f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
                    })
            except Exception as e:
                logger.warning(f"Error searching in video {vid}: {str(e)}")
                continue
                
    # Sort results by best match score
    for r in results:
        r["best_score"] = max(m["score"] for m in r["matches"])
    results.sort(key=lambda x: x["best_score"], reverse=True)
    
    # Limit to top 50 to avoid massive payloads
    top_results = results[:50]

    logger.info(f"Search complete: '{query}' — {len(top_results)} videos returned out of {len(results)} total matches.")'''

if "candidate_meta = {}" in content:
    content = content.replace(old_search_logic, new_search_logic)
    
# Also modify the return statement
content = content.replace('        "results": results', '        "results": top_results')

with open('backend/app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated app.py successfully.")
