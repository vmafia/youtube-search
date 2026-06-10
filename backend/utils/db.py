import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages Firebase Firestore operations, with fallback to local JSON cache."""
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.db = None
        self.use_firebase = False

        # Attempt to initialize Firebase Admin SDK
        firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        project_id = os.environ.get("FIREBASE_PROJECT_ID", "youtube-transcript-search")

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
                logger.error(f"Failed to initialize Firebase with service account JSON: {str(e)}")
        else:
            logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON is not defined. Falling back to local file caching.")

    def _get_local_path(self, collection: str, key: str) -> str:
        # Sanitise key for filesystem
        clean_key = "".join([c if c.isalnum() else "_" for c in key])
        return os.path.join(self.cache_dir, collection, f"{clean_key}.json")

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
        local_path = self._get_local_path(collection, doc_id)
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    logger.info(f"Retrieved {doc_id} from local cache ({collection})")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Local cache read error for {doc_id}: {str(e)}")
        return None

    def set_document(self, collection: str, doc_id: str, data: Any) -> None:
        """Saves a document to Firestore and duplicates locally."""
        if self.use_firebase and self.db:
            try:
                doc_ref = self.db.collection(collection).document(doc_id)
                doc_ref.set({"data": data})
                logger.info(f"Saved document {doc_id} to Firestore ({collection})")
            except Exception as e:
                logger.error(f"Firestore write error for {doc_id} in {collection}: {str(e)}")

        # Always write to local cache as fallback/duplicate
        local_path = self._get_local_path(collection, doc_id)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved {doc_id} to local cache ({collection})")
        except Exception as e:
            logger.error(f"Local cache write error for {doc_id}: {str(e)}")
