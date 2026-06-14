import os
import json
import logging
import gzip
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages Firebase Firestore operations, with fallback to local JSON cache."""
    def __init__(self, cache_dir: str):
        self.writable_cache_dir = cache_dir
        self.bundled_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
        self.db = None
        self.use_firebase = False
        self.init_error = None

        # Attempt to initialize Firebase Admin SDK
        firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        project_id = os.environ.get("FIREBASE_PROJECT_ID", "transcript-search-b162c")

        if os.environ.get("VERCEL"):
            self._ensure_vercel_cache()

        if firebase_json:
            try:
                # If json is a path to a file
                if os.path.exists(firebase_json):
                    cred = credentials.Certificate(firebase_json)
                else:
                    # Treat it as a direct JSON string
                    cred_dict = json.loads(firebase_json)
                    cred = credentials.Certificate(cred_dict)
                
                firebase_admin.initialize_app(cred, {
                    'projectId': project_id
                })
                self.db = firestore.client()
                self.use_firebase = True
                logger.info("Successfully initialized Firebase Firestore")
            except Exception as e:
                self.init_error = str(e)
                logger.error(f"Failed to initialize Firebase with service account JSON: {str(e)}")
        else:
            self.init_error = "FIREBASE_SERVICE_ACCOUNT_JSON env var is missing"
            logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON is not defined. Falling back to local file caching.")

    def _ensure_vercel_cache(self):
        """On Vercel, downloads all_transcripts.json.gz from GitHub into /tmp if not already present."""
        target_file = os.path.join(self.writable_cache_dir, "all_transcripts.json.gz")
        if not os.path.exists(target_file):
            try:
                import urllib.request
                import io
                logger.info("Vercel environment detected. Downloading all_transcripts.json.gz from GitHub...")
                url = "https://raw.githubusercontent.com/vmafia/youtube-search/main/backend/cache/all_transcripts.json.gz"
                response = urllib.request.urlopen(url)
                logger.info("Download complete. Saving to /tmp/all_transcripts.json.gz...")
                os.makedirs(self.writable_cache_dir, exist_ok=True)
                with open(target_file, 'wb') as f:
                    f.write(response.read())
                logger.info("Cache file saved successfully.")
            except Exception as e:
                logger.error(f"Failed to download cache on Vercel: {e}")

    def _get_local_paths(self, collection: str, key: str) -> list[str]:
        clean_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        return [
            os.path.join(self.writable_cache_dir, collection, f"{clean_key}.json.gz"),
            os.path.join(self.bundled_cache_dir, collection, f"{clean_key}.json.gz")
        ]

    def _get_writable_path(self, collection: str, key: str) -> str:
        clean_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        return os.path.join(self.writable_cache_dir, collection, f"{clean_key}.json.gz")

    def get_document(self, collection: str, doc_id: str) -> Optional[Any]:
        """Gets a document from Firestore or falls back to local cache."""
        if self.use_firebase and self.db:
            try:
                doc_ref = self.db.collection(collection).document(doc_id)
                doc = doc_ref.get()
                if doc.exists:
                    logger.info(f"Retrieved document {doc_id} from Firestore ({collection})")
                    return doc.to_dict().get("data")
            except Exception as e:
                logger.error(f"Firestore get error for {doc_id} in {collection}: {str(e)}")
        
        # Fallback to local files
        for local_path in self._get_local_paths(collection, doc_id):
            if os.path.exists(local_path):
                try:
                    with gzip.open(local_path, "rt", encoding="utf-8") as f:
                        logger.info(f"Retrieved {doc_id} from local cache ({collection})")
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Local cache read error for {doc_id} in {local_path}: {str(e)}")
        return None

    def get_all_document_ids(self, collection: str) -> list:
        """Gets all document IDs in a collection from Firestore or falls back to local cache."""
        if self.use_firebase and self.db:
            try:
                docs = self.db.collection(collection).select([]).stream()
                return [doc.id for doc in docs]
            except Exception as e:
                logger.error(f"Firestore list_documents error in {collection}: {str(e)}")

        # Fallback to local files
        docs = set()
        for c_dir in [self.writable_cache_dir, self.bundled_cache_dir]:
            local_dir = os.path.join(c_dir, collection)
            if os.path.exists(local_dir):
                try:
                    for filename in os.listdir(local_dir):
                        if filename.endswith(".json.gz"):
                            docs.add(filename[:-8])
                except Exception as e:
                    logger.error(f"Local cache list error for {collection} in {c_dir}: {str(e)}")
        return list(docs)


    def set_document(self, collection: str, doc_id: str, data: Any) -> None:
        """Saves a document to Firestore and duplicates locally."""
        if self.use_firebase and self.db:
            try:
                doc_ref = self.db.collection(collection).document(doc_id)
                doc_ref.set({"data": data})
                logger.info(f"Saved document {doc_id} to Firestore ({collection})")
            except Exception as e:
                logger.error(f"Firestore write error for {doc_id} in {collection}: {str(e)}")

        # Always write to writable local cache as fallback/duplicate
        local_path = self._get_writable_path(collection, doc_id)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with gzip.open(local_path, "wt", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Saved {doc_id} to local cache ({collection})")
        except Exception as e:
            logger.error(f"Local cache write error for {doc_id}: {str(e)}")
