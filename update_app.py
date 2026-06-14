import os

content = open('backend/app.py', 'r', encoding='utf-8').read()
content = content.replace(
'''        if not youtube_client.db_manager.use_firebase or not db:
            cache_path = os.path.join(youtube_client.db_manager.cache_dir, "transcripts")
            transcribed_ids = []
            if os.path.exists(cache_path):
                for f_name in os.listdir(cache_path):
                    if f_name.endswith(".json.gz"):
                        vid = f_name[:-8]
                        transcribed_ids.append(vid)
            
            return jsonify({
                "total_videos": len(channel_data.get("videos", [])),
                "transcribed_count": len(transcribed_ids),
                "transcribed_ids": transcribed_ids
            }), 200''',
'''        if not youtube_client.db_manager.use_firebase or not db:
            transcribed_ids = youtube_client.db_manager.list_documents("transcripts")
            
            return jsonify({
                "total_videos": len(channel_data.get("videos", [])),
                "transcribed_count": len(transcribed_ids),
                "transcribed_ids": transcribed_ids
            }), 200'''
)

# And another place where cache_path is used to read all transcripts
content = content.replace(
'''            cache_path = os.path.join(youtube_client.db_manager.cache_dir, "transcripts")
            if os.path.exists(cache_path):
                for f_name in os.listdir(cache_path):
                    if f_name.endswith(".json.gz"):
                        vid = f_name[:-8]
                        local_path = os.path.join(cache_path, f_name)
                        with gzip.open(local_path, "rt", encoding="utf-8") as f:
                            data = json.load(f)''',
'''            # Fetch all documents using the db_manager directly
            for vid in youtube_client.db_manager.list_documents("transcripts"):
                data = youtube_client.db_manager.get_document("transcripts", vid)
                if data:'''
)

with open('backend/app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated app.py")
