import sys
import time
import json
import os
import pydantic
import re
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.utils.youtube import YouTubeClient
from dotenv import load_dotenv

load_dotenv()

def scrape_transcript(page, video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[{video_id}] Navigating to {url}...")
    
    # Retry goto in case of interrupted navigation
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded")
            break
        except Exception as e:
            print(f"[{video_id}] Goto failed (attempt {attempt+1}): {e}")
            time.sleep(2)
    
    # Let page settle
    page.wait_for_timeout(3000)
    
    # Handle cookie consent if present
    try:
        consent_btn = page.get_by_role("button", name=re.compile(r"Reject all|Accept all|Agree|I agree", re.IGNORECASE)).first
        if consent_btn.is_visible(timeout=3000):
            print(f"[{video_id}] Clicking cookie consent...")
            consent_btn.click()
            time.sleep(1)
    except Exception:
        pass
        
    print(f"[{video_id}] Waiting for description expand button...")
    try:
        page.wait_for_selector('#expand', timeout=5000)
        page.click('#expand')
        time.sleep(1)
    except Exception as e:
        print(f"[{video_id}] Expand button not found or already expanded.")
        
    print(f"[{video_id}] Looking for 'Show transcript' button...")
    try:
        # Avoid clicking the video player's CC button by targeting the description area specifically
        btn = page.locator('ytd-video-description-transcript-section-renderer button')
        if btn.is_visible(timeout=2000):
            btn.click()
        else:
            # Fallback to looking in the description inner panel
            desc_btn = page.locator('#description-inner').get_by_role("button", name=re.compile(r"Show transcript|แสดงคำบรรยาย", re.IGNORECASE)).first
            desc_btn.click()
        time.sleep(2)
    except Exception as e:
        print(f"[{video_id}] Transcript button not found! Maybe CC is disabled.")
        return None
        
    print(f"[{video_id}] Extracting transcript segments...")
    try:
        page.wait_for_selector('ytd-transcript-segment-renderer', timeout=10000)
        segments = page.query_selector_all('ytd-transcript-segment-renderer')
        
        result = []
        for seg in segments:
            time_text = seg.query_selector('.segment-timestamp').inner_text().strip()
            text = seg.query_selector('.segment-text').inner_text().strip()
            
            parts = time_text.split(':')
            if len(parts) == 3:
                start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                start_sec = int(parts[0]) * 60 + int(parts[1])
            else:
                start_sec = float(time_text)
                
            result.append({
                "text": text,
                "start": float(start_sec),
                "duration": 2.0 
            })
            
        print(f"[{video_id}] Scraped {len(result)} segments!")
        return result
    except Exception as e:
        if "No node found" in str(e) or "Timeout" in str(e):
            print(f"[{video_id}] Failed to extract segments: Timeout or missing elements")
        else:
            print(f"[{video_id}] Failed to extract segments: {e}")
        return None

def main():
    client = YouTubeClient('firebase')
    user_data_dir = os.path.join(os.path.dirname(__file__), 'playwright_profile')
    
    print("Fetching videos to scrape from Firebase...")
    docs = client.db_manager.db.collection('transcripts').stream()
    videos_to_scrape = []
    for doc in docs:
        data = doc.to_dict()
        if 'segments' not in data or not data['segments']:
            videos_to_scrape.append(doc.id)
            
    print(f"Found {len(videos_to_scrape)} videos to scrape.")
    if not videos_to_scrape:
        print("Everything is already scraped!")
        return
    
    print("Launching persistent Chrome profile...")
    with sync_playwright() as p:
        # Launch persistent context
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",  # Use the real Google Chrome installed on the computer
            headless=False,
            locale='th-TH',
            args=['--disable-blink-features=AutomationControlled'] # Hide automation flag
        )
        page = context.new_page()
        
        # Go to YouTube to let the user login
        page.goto('https://www.youtube.com/')
        print("\n\n=======================================================")
        print("ACTION REQUIRED: PLEASE LOG IN TO YOUTUBE IN THE CHROME WINDOW!")
        print("After you are successfully logged in, press ENTER in this console to continue.")
        print("=======================================================\n\n")
        
        # Wait for user input
        input("Press ENTER here to start scraping...")
        
        count = 0
        for vid in videos_to_scrape:
            count += 1
            print(f"--- Scraping {count}/{len(videos_to_scrape)} : {vid} ---")
            transcript = scrape_transcript(page, vid)
            doc_ref = client.db_manager.db.collection('transcripts').document(vid)
            if transcript:
                print(f"[{vid}] Success! Saving {len(transcript)} segments to Firebase...")
                doc_ref.set({"segments": transcript}, merge=True)
            else:
                print(f"[{vid}] No transcript found or failed. Marking as failed/unavailable.")
                doc_ref.set({"scrape_status": "failed_or_unavailable"}, merge=True)
            
            # Brief pause between videos
            time.sleep(1)
            
        print("Finished scraping all videos!")
        time.sleep(10)
        context.close()

if __name__ == "__main__":
    main()
