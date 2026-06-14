import os

content = open('backend/utils/db.py', 'r', encoding='utf-8').read()
content = content.replace(
'''    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.db = None
        self.use_firebase = False
        self.init_error = None''',
'''    def __init__(self, cache_dir: str):
        self.writable_cache_dir = cache_dir
        self.bundled_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
        self.db = None
        self.use_firebase = False
        self.init_error = None'''
)

content = content.replace(
'''    def _get_local_path(self, collection: str, key: str) -> str:
        # Sanitise key for filesystem, preserving - and _ which are valid in YouTube IDs
        clean_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        return os.path.join(self.cache_dir, collection, f"{clean_key}.json.gz")''',
'''    def _get_local_paths(self, collection: str, key: str) -> list[str]:
        clean_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        return [
            os.path.join(self.writable_cache_dir, collection, f"{clean_key}.json.gz"),
            os.path.join(self.bundled_cache_dir, collection, f"{clean_key}.json.gz")
        ]

    def _get_writable_path(self, collection: str, key: str) -> str:
        clean_key = "".join([c if c.isalnum() or c in "-_" else "_" for c in key])
        return os.path.join(self.writable_cache_dir, collection, f"{clean_key}.json.gz")'''
)

content = content.replace(
'''        # Fallback to local files
        local_path = self._get_local_path(collection, doc_id)
        if os.path.exists(local_path):
            try:
                with gzip.open(local_path, "rt", encoding="utf-8") as f:
                    logger.info(f"Retrieved {doc_id} from local cache ({collection})")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Local cache read error for {doc_id}: {str(e)}")
        return None''',
'''        # Fallback to local files
        for local_path in self._get_local_paths(collection, doc_id):
            if os.path.exists(local_path):
                try:
                    with gzip.open(local_path, "rt", encoding="utf-8") as f:
                        logger.info(f"Retrieved {doc_id} from local cache ({collection})")
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Local cache read error for {doc_id} in {local_path}: {str(e)}")
        return None'''
)

content = content.replace(
'''        # Fallback to local files
        local_dir = os.path.join(self.cache_dir, collection)
        if os.path.exists(local_dir):
            try:
                docs = []
                for filename in os.listdir(local_dir):
                    if filename.endswith(".json.gz"):
                        docs.append(filename[:-8])
                return docs
            except Exception as e:
                logger.error(f"Local cache list error for {collection}: {str(e)}")
        return []''',
'''        # Fallback to local files
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
        return list(docs)'''
)

content = content.replace(
'''        # Always write to local cache as fallback/duplicate
        local_path = self._get_local_path(collection, doc_id)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with gzip.open(local_path, "wt", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Saved {doc_id} to local cache ({collection})")
        except Exception as e:
            logger.error(f"Local cache write error for {doc_id}: {str(e)}")''',
'''        # Always write to writable local cache as fallback/duplicate
        local_path = self._get_writable_path(collection, doc_id)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with gzip.open(local_path, "wt", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Saved {doc_id} to local cache ({collection})")
        except Exception as e:
            logger.error(f"Local cache write error for {doc_id}: {str(e)}")'''
)

with open('backend/utils/db.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated db.py")
