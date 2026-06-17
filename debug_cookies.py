import os
print("cwd:", os.getcwd())
print("script dir:", os.path.dirname(os.path.abspath(__file__)))
for name in ['cookies_new.txt', 'cookies.txt', 'youtube_cookies.txt']:
    p1 = os.path.join(os.getcwd(), name)
    p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    print(f"{name}: cwd_exists={os.path.exists(p1)}, script_exists={os.path.exists(p2)}")
