import os

project_dir = r"C:\Users\hp\Documents\GitHub\youtube-search"
for root, dirs, files in os.walk(project_dir):
    if ".git" in root or "node_modules" in root or "venv" in root:
        continue
    for file in files:
        if file.endswith((".py", ".ts", ".tsx", ".js", ".json")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        if "estimated" in line:
                            print(f"{path}:{line_no}: {line.strip()}")
            except Exception as e:
                pass
