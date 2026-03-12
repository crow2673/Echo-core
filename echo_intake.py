#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path("echo_memory.json")

def add_income_source(name, type, expected_pay):
    if not MEMORY_FILE.exists(): return
    memory = json.loads(MEMORY_FILE.read_text())
    
    capsule_id = f"INCOME:{name.replace(' ', '_').upper()}"
    
    new_source = {
        "capsule_id": capsule_id,
        "purpose": f"Monitor and automate income from {name}",
        "type": type,
        "status": "pending",
        "expected_pay": expected_pay,
        "created_at": datetime.now().isoformat(),
        "verified": False,
        "notes": "Added via Echo Intake. Awaiting automation logic."
    }
    
    memory.append(new_source)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))
    print(f"[+] Echo now tracking: {name} (${expected_pay})")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True, help="App or Site Name")
    p.add_argument("--type", default="Passive", help="Manual, Passive, or Hybrid")
    p.add_argument("--pay", default="Unknown", help="Estimated pay per day/task")
    args = p.parse_args()
    
    add_income_source(args.name, args.type, args.pay)
