#!/usr/bin/env python3
import json
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
MEMORY_FILE = BASE_DIR / "echo_memory.json"
TRIGGER_FILE = BASE_DIR / "work_detected.txt"

def send_notification(title, message):
    try:
        # This sends a real Ubuntu desktop notification
        subprocess.run(["notify-send", "-i", "utilities-terminal", title, message])
    except Exception as e:
        print(f"Notification error: {e}")

def update_task_status(capsule_id, status, note):
    try:
        memory = json.loads(MEMORY_FILE.read_text())
        for cap in memory:
            if cap.get("capsule_id") == capsule_id:
                cap["status"] = status
                cap["verified"] = False
                cap.setdefault("result_notes", [])
                cap["result_notes"].append(f"[{time.ctime()}] {note}")
        MEMORY_FILE.write_text(json.dumps(memory, indent=2))
        return True
    except Exception:
        return False

print("--- Outlier System Scan ---")
if TRIGGER_FILE.exists():
    msg = "REAL WORK FOUND: Outlier tasks are waiting!"
    print(f"\033[92m[!] {msg}\033[0m")
    
    # Send the alert to your desktop!
    send_notification("Echo System Alert", "New Outlier tasks detected in queue!")
    
    update_task_status("TASK:MasterFirst:2", "pending", msg)
else:
    print("[?] Scan complete: Queue is empty.")
    update_task_status("TASK:MasterFirst:2", "done", "Scan finished: No work found.")
