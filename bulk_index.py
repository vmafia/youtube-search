"""
bulk_index.py -- ดึง transcript ทุกคลิปใน channel เข้า cache อัตโนมัติ
ทำงานแบบ batch, แสดง progress, และ resume ได้ถ้าหยุดกลางคัน

วิธีใช้:
    python bulk_index.py
    python bulk_index.py --channel @AssabiqoonPublisher
    python bulk_index.py --channel @AssabiqoonPublisher --batch-size 50 --url http://localhost:5000
"""

import io
import sys
# Force UTF-8 output on Windows (แก้ปัญหา cp874 encoding)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timedelta

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_CHANNEL   = "@AssabiqoonPublisher"
DEFAULT_API_URL   = "http://localhost:5000"
DEFAULT_BATCH     = 50        # video ต่อ batch
DEFAULT_DELAY     = 0.5       # วินาทีพัก ระหว่าง batch (ป้องกัน rate limit)
PROGRESS_FILE     = "bulk_index_progress.json"   # เก็บ state สำหรับ resume
# ──────────────────────────────────────────────────────────────────────────────


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[i]", "OK": "[OK]", "WARN": "[!]", "ERR": "[X]", "PROG": "[~]"}
    icon = icons.get(level, "   ")
    print(f"[{ts}] {icon} {msg}")


def fetch_all_video_ids(api_url: str, channel: str) -> list:
    """ดึง video IDs ทั้งหมด — ลอง local cache ก่อน แล้วค่อย fallback ไป API"""

    # --- ลอง local cache ก่อน (เร็วกว่ามาก) ---
    cache_dir = os.path.join(os.path.dirname(__file__), "backend", "cache", "channel_videos")
    if os.path.isdir(cache_dir):
        # หาไฟล์ cache ทั้งหมดที่ตรงกับ channel นี้ แล้วเลือกไฟล์ที่ใหญ่ที่สุด (มีวิดีโอมากที่สุด)
        clean = channel.replace("@", "").replace("/", "_")
        candidates = []
        for fname in os.listdir(cache_dir):
            if clean in fname and fname.endswith(".json"):
                fpath = os.path.join(cache_dir, fname)
                candidates.append((os.path.getsize(fpath), fpath, fname))

        # เรียงจากใหญ่ไปเล็ก เอาไฟล์ที่ใหญ่ที่สุดก่อน
        candidates.sort(reverse=True)

        for _, fpath, fname in candidates:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    videos = json.load(f)
                if isinstance(videos, list) and videos:
                    ids = [v["id"] for v in videos if "id" in v]
                    log(f"โหลดจาก local cache: {len(ids):,} คลิป ({fname})", "OK")
                    return ids
            except Exception as e:
                log(f"อ่าน cache ไม่ได้ ({fname}): {e}", "WARN")

    # --- fallback: เรียก API ---
    log(f"ไม่พบ local cache, กำลังดึง video list ของ {channel} จาก API ...", "INFO")
    try:
        r = requests.post(
            f"{api_url}/api/channel-videos",
            json={"channel_name": channel, "limit": 5000},
            timeout=120   # เพิ่มเป็น 2 นาที
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        log(f"พบวิดีโอทั้งหมด {len(videos):,} คลิป", "OK")
        return [v["id"] for v in videos]
    except Exception as e:
        log(f"ดึง channel videos ไม่ได้: {e}", "ERR")
        sys.exit(1)


def load_progress(channel: str) -> dict:
    """โหลด progress จากไฟล์ (สำหรับ resume)"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("channel") == channel:
                return data
        except Exception:
            pass
    return {"channel": channel, "done": [], "failed": []}


def save_progress(state: dict):
    """บันทึก progress ลงไฟล์"""
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"บันทึก progress ไม่ได้: {e}", "WARN")


def index_batch(api_url: str, video_ids: list) -> dict:
    """ส่ง batch ไปยัง /api/bulk-index endpoint"""
    r = requests.post(
        f"{api_url}/api/bulk-index",
        json={"video_ids": video_ids},
        timeout=300   # 5 นาทีต่อ batch
    )
    r.raise_for_status()
    return r.json()


def format_eta(seconds: float) -> str:
    """แปลงวินาทีเป็น HH:MM:SS"""
    return str(timedelta(seconds=int(seconds)))


def print_summary(total, indexed, cached, failed, elapsed):
    """แสดงสรุปผลท้ายสุด"""
    print("\n" + "=" * 55)
    print("  [DONE]  สรุปผล Bulk Index")
    print("=" * 55)
    print(f"  วิดีโอทั้งหมด          : {total:,} คลิป")
    print(f"  [OK] Index ใหม่        : {indexed:,} คลิป")
    print(f"  [cache] มีอยู่แล้ว     : {cached:,} คลิป")
    print(f"  [X] ดึงไม่ได้          : {failed:,} คลิป")
    print(f"  [time] ใช้เวลา         : {format_eta(elapsed)}")
    print("=" * 55)
    if failed:
        print(f"\n  [!] คลิปที่ดึงไม่ได้ส่วนใหญ่คือคลิปที่ YouTube ปิด subtitle")
        print(f"      หรือเป็นคลิปสั้นที่ไม่มี transcript")
    print()


def run(channel: str, api_url: str, batch_size: int, delay: float, resume: bool):
    start_time = time.time()

    # โหลด video IDs ทั้งหมด
    all_ids = fetch_all_video_ids(api_url, channel)
    total = len(all_ids)

    # โหลด progress เดิม (ถ้า resume)
    state = load_progress(channel) if resume else {"channel": channel, "done": [], "failed": []}
    already_done = set(state.get("done", []) + state.get("failed", []))

    # กรองเฉพาะที่ยังไม่ได้ทำ
    remaining = [vid for vid in all_ids if vid not in already_done]

    if not remaining:
        log("ทุกคลิป index ครบแล้ว! ไม่มีอะไรต้องทำเพิ่ม 🎉", "OK")
        return

    if already_done:
        log(f"Resume: ทำไปแล้ว {len(already_done):,} คลิป, เหลือ {len(remaining):,} คลิป", "INFO")
    else:
        log(f"เริ่ม index {len(remaining):,} คลิป (batch ละ {batch_size})", "INFO")

    print()

    total_indexed  = 0
    total_cached   = 0
    total_failed   = 0
    processed      = 0
    batches        = [remaining[i:i+batch_size] for i in range(0, len(remaining), batch_size)]
    num_batches    = len(batches)

    for b_idx, batch in enumerate(batches, 1):
        batch_start = time.time()

        # แสดง progress bar
        pct = (b_idx - 1) / num_batches
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)

        # คำนวณ ETA
        elapsed_so_far = time.time() - start_time
        if b_idx > 1:
            rate = processed / elapsed_so_far   # videos/sec
            eta_sec = (len(remaining) - processed) / rate if rate > 0 else 0
            eta_str = format_eta(eta_sec)
        else:
            eta_str = "กำลังคำนวณ..."

        print(
            f"\r  [{bar}] Batch {b_idx}/{num_batches} "
            f"| {processed:,}/{len(remaining):,} คลิป "
            f"| ETA: {eta_str}   ",
            end="", flush=True
        )

        # ส่ง batch ไปยัง API
        try:
            result = index_batch(api_url, batch)
            b_indexed = len(result.get("indexed", []))
            b_cached  = len(result.get("already_cached", []))
            b_failed  = len(result.get("failed", []))

            total_indexed += b_indexed
            total_cached  += b_cached
            total_failed  += b_failed
            processed     += len(batch)

            state["done"].extend(result.get("indexed", []) + result.get("already_cached", []))
            state["failed"].extend(result.get("failed", []))
            save_progress(state)

            batch_elapsed = time.time() - batch_start
            # แสดงรายละเอียด batch ที่เสร็จ (ขึ้นบรรทัดใหม่เฉพาะกรณีพิเศษ)
            if b_failed > 0:
                print(
                    f"\n  ⚠️  Batch {b_idx}: "
                    f"+{b_indexed} indexed, {b_cached} cached, {b_failed} failed "
                    f"({batch_elapsed:.1f}s)"
                )

        except requests.exceptions.Timeout:
            log(f"\nBatch {b_idx} timeout — ข้ามไปก่อน", "WARN")
            state["failed"].extend(batch)
            total_failed += len(batch)
            processed    += len(batch)
            save_progress(state)

        except Exception as e:
            log(f"\nBatch {b_idx} error: {e}", "ERR")
            state["failed"].extend(batch)
            total_failed += len(batch)
            processed    += len(batch)
            save_progress(state)

        # พักระหว่าง batch
        if b_idx < num_batches and delay > 0:
            time.sleep(delay)

    # จบแล้ว
    print()  # ขึ้นบรรทัดใหม่หลัง progress bar
    elapsed = time.time() - start_time

    # ลบ progress file เมื่อเสร็จสมบูรณ์
    if total_failed == 0 and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        log("ลบ progress file แล้ว (ทำครบทุกคลิป)", "OK")

    print_summary(
        total=total,
        indexed=total_indexed,
        cached=total_cached,
        failed=total_failed,
        elapsed=elapsed
    )


def main():
    parser = argparse.ArgumentParser(
        description="Bulk-index YouTube transcripts for a channel"
    )
    parser.add_argument(
        "--channel", "-c",
        default=DEFAULT_CHANNEL,
        help=f"YouTube channel handle (default: {DEFAULT_CHANNEL})"
    )
    parser.add_argument(
        "--url", "-u",
        default=DEFAULT_API_URL,
        help=f"Backend API URL (default: {DEFAULT_API_URL})"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=DEFAULT_BATCH,
        help=f"Number of videos per batch (default: {DEFAULT_BATCH})"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between batches in seconds (default: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="เริ่มใหม่ตั้งแต่ต้น ไม่ต่อจาก progress ที่หยุดไว้"
    )
    args = parser.parse_args()

    print()
    print("+" + "-" * 46 + "+")
    print("|    YouTube Transcript Bulk Indexer       |")
    print("+" + "-" * 46 + "+")
    print(f"  Channel   : {args.channel}")
    print(f"  API URL   : {args.url}")
    print(f"  Batch size: {args.batch_size} videos")
    print(f"  Delay     : {args.delay}s between batches")
    print(f"  Resume    : {'ไม่' if args.no_resume else 'ใช่ (ต่อจากที่ค้างไว้)'}")
    print()

    # ตรวจว่า backend ขึ้นอยู่ไหม
    try:
        r = requests.get(f"{args.url}/api/health", timeout=5)
        r.raise_for_status()
        health = r.json()
        db_type = health.get("database", "unknown")
        log(f"Backend online ✓  (database: {db_type})", "OK")
        if db_type == "local_cache":
            log("ใช้ local cache — transcript จะถูกบันทึกใน backend/cache/transcripts/", "INFO")
        else:
            log("ใช้ Firebase Firestore — transcript จะถูกบันทึกใน cloud", "INFO")
    except Exception as e:
        log(f"ติดต่อ backend ไม่ได้: {e}", "ERR")
        log(f"ตรวจสอบว่า backend รันอยู่ที่ {args.url} ก่อน", "WARN")
        sys.exit(1)

    print()

    try:
        run(
            channel=args.channel,
            api_url=args.url,
            batch_size=args.batch_size,
            delay=args.delay,
            resume=not args.no_resume
        )
    except KeyboardInterrupt:
        print()
        log("หยุดโดยผู้ใช้ — progress ถูกบันทึกแล้ว สามารถรันใหม่เพื่อ resume ได้", "WARN")
        sys.exit(0)


if __name__ == "__main__":
    main()
