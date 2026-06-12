import sys

sys.stdout.reconfigure(encoding='utf-8')
log_path = r"C:\Users\HP\.gemini\antigravity\brain\7e54ae1c-33cc-4246-a821-877c55c6a957\.system_generated\tasks\task-658.log"
try:
    with open(log_path, "r", encoding="utf-8") as f:
        print(f.read())
except Exception as e:
    print("Error reading log:", e)
