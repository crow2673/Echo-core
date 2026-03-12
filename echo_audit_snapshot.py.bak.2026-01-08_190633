#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return []

def compute_confidence(capsule):
    """
    Simple confidence metric:
    - Verified: +40
    - Has timestamp: +30
    - Purpose is known: +20
    - Key items not empty: +10
    Max = 100
    """
    confidence = 0
    if capsule.get("verified", False):
        confidence += 40
    if capsule.get("timestamp"):
        confidence += 30
    if capsule.get("purpose") not in ["Unknown", ""]:
        confidence += 20
    if capsule.get("key_items"):
        confidence += 10
    return min(confidence, 100)

def classify_capsules(memory):
    completed = []
    pending = []
    queued = []
    for cap in memory:
        if cap.get("verified") and cap.get("timestamp"):
            completed.append(cap)
        elif cap.get("purpose") in ["CurrentGoal:SubTasks", "MasterFirst"]:
            queued.append(cap)
        else:
            pending.append(cap)
    return completed, pending, queued

def print_audit():
    memory = load_memory()
    completed, pending, queued = classify_capsules(memory)
    
    print(f"=== Echo Audit Snapshot ===\nGenerated: {datetime.now()}\nTotal capsules: {len(memory)}\n")
    
    def print_capsules(title, capsules):
        print(f"--- {title} ---")
        for cap in capsules:
            conf = compute_confidence(cap)
            print(f"{cap.get('purpose', 'Unknown')} | ID: {cap.get('capsule_id', 'N/A')} | Timestamp: {cap.get('timestamp', 'N/A')} | Confidence: {conf}%")
        print()
    
    print_capsules("Completed", completed)
    print_capsules("Pending", pending)
    print_capsules("Queued Workflows/Commands", queued)

if __name__ == "__main__":
    print_audit()
