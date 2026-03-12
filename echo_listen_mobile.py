#!/usr/bin/env python3
import os
import json
import subprocess
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")

def process_notification(app_name, message):
    print(f"[*] Processing mobile alert from {app_name}: {message}")
    
    # Example Logic: If the notification mentions money
    if "$" in message or "earned" in message.lower():
        if MEMORY_FILE.exists():
            memory = json.loads(MEMORY_FILE.read_text())
            # Find the income source in memory or create a new one
            capsule_id = f"INCOME:{app_name.upper()}"
            
            found = False
            for cap in memory:
                if cap.get("capsule_id") == capsule_id:
                    cap.setdefault("result_notes", []).append(f"Mobile Alert: {message}")
                    cap["status"] = "verified"
                    found = True
            
            if not found:
                print(f"[!] New income source detected: {app_name}")
                # You can call echo_intake.py here automatically!

            MEMORY_FILE.write_text(json.dumps(memory, indent=2))
            subprocess.run(["notify-send", "Echo Mobile Sync", f"Logged income from {app_name}"])

if __name__ == "__main__":
    # This is a placeholder. In a full setup, we would use 'dbus-monitor' 
    # to pipe real phone notifications into this function.
    print("Echo Mobile Listener: Active. Waiting for DBus signals...")
