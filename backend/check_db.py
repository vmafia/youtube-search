import sys
import os
sys.path.append(os.path.abspath('.'))

from backend.utils.search_db import get_db_client
client = get_db_client()
rs = client.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='videos'")
for r in rs.rows: print(r[0])
client.close()
