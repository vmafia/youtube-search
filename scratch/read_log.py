import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\HP\.gemini\antigravity\brain\7e54ae1c-33cc-4246-a821-877c55c6a957\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        step = data.get("step_index")
        if step and 650 <= step <= 680:
            if "task-658" in str(data):
                print(f"STEP {step} | source: {data.get('source')} | type: {data.get('type')}")
                for k, v in data.items():
                    if k not in ["step_index", "source", "type", "created_at"]:
                        print(f"  {k}: {repr(v)[:500]}")
                print("-" * 30)
