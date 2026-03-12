#!/usr/bin/env python3
import subprocess
import json
import time
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")

def sync():
    try:
        res = subprocess.run(["yagna", "payment", "status", "--json"], capture_output=True, text=True)
        data = json.loads(res.stdout)
        glm = data.get('totalAmount', '0.00')
    except:
        glm = "0.00"

    if MEMORY_FILE.exists():
        memory = json.loads(MEMORY_FILE.read_text())
        # Add or update the Golem income source
        found = False
        for cap in memory:
            if cap.get("capsule_id") == "INCOME:GOLEM":
                cap["notes"] = f"Current Balance: {glm} GLM"
                cap["status"] = "active"
                found = True
        
        if not found:
            memory.append({
                "capsule_id": "INCOME:GOLEM",
                "purpose": "Golem Provider Earnings",
                "status": "active",
                "notes": f"Current Balance: {glm} GLM"
            })
        
        MEMORY_FILE.write_text(json.dumps(memory, indent=2))
        print(f"[+] Golem Sync: {glm} GLM")

if __name__ == "__main__":
    sync()
