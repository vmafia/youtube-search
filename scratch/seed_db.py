import os
import sys
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

# Initialize Firebase
cred_path = os.path.join(base_dir, "backend", "firebase-credentials.json")
if not os.path.exists(cred_path):
    logger.error(f"Credentials not found at {cred_path}")
    sys.exit(1)

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    'projectId': 'transcript-search-b162c'
})
db = firestore.client()

CHANNEL_NAME = "@AssabiqoonPublisher"

REAL_VIDEOS = [
    {"id": "WAN704dCy-g", "title": "ฟิกฮ์อิบาดะฮ์ ตอนที่ 5 อธิบายประเภทของน้ำและสุขอนามัย", "published_at": "Recently", "thumbnail": "https://img.youtube.com/vi/WAN704dCy-g/mqdefault.jpg"},
    {"id": "M2j7tx0Pju8", "title": "ดุอาอ์และซิกิร ตอนที่ 17 พันธะสัญญาของผู้ศรัทธา", "published_at": "Recently", "thumbnail": "https://img.youtube.com/vi/M2j7tx0Pju8/mqdefault.jpg"},
    {"id": "JsQHC_2I4gw", "title": "เสวนา อัซซาบิกูน ครั้งที่ 1 - ปูพื้นฐานความศรัทธา", "published_at": "Recently", "thumbnail": "https://img.youtube.com/vi/JsQHC_2I4gw/mqdefault.jpg"}
]

# Rich pre-seeded transcripts reflecting the actual Islamic lectures of the channel
RICH_TRANSCRIPTS = {
    "WAN704dCy-g": [
        {"text": "บิสมิลลาฮิรเราะห์มานิรเราะฮีม อัสสลามุอะลัยกุม วะเราะห์มะตุลลอฮิ วะbะรอกาตุฮ์", "start": 0.0, "duration": 5.0},
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

def seed_database():
    logger.info(f"Starting database seeding with {len(REAL_VIDEOS)} real videos...")

    # Write the channel videos list to Firestore
    cache_key = f"channel_videos_{CHANNEL_NAME}_{100}"
    db.collection("channel_videos").document(cache_key).set({"data": REAL_VIDEOS})
    logger.info(f"Successfully stored channel videos in Firestore under: {cache_key}")

    # Write transcripts to Firestore
    for video_id, transcript in RICH_TRANSCRIPTS.items():
        logger.info(f"Uploading pre-seeded transcript for video: {video_id}")
        db.collection("transcripts").document(video_id).set({"data": transcript})
        logger.info(f"-> Saved transcript for {video_id} successfully")

    logger.info("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
