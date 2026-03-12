import json
from pathlib import Path
CHAT_FILE = Path("echo_chat_memory.json")
MEMORY_FILE = Path("echo_memory.json")

if CHAT_FILE.exists():
    with open(CHAT_FILE) as f:
        chat_data = json.load(f)
    chat_event = {"type": "chat_history", "timestamp": float(Path(CHAT_FILE).stat().st_mtime), "data": chat_data}
    with open(MEMORY_FILE, 'a') as f:
        f.write(json.dumps(chat_event) + '\n')
    print(f"✓ Chat memory merged! ({len(chat_data)} messages)")
else:
    print("No echo_chat_memory.json found")
