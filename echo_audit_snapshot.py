#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_memory():
    if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 0:
        try:
            data = json.loads(MEMORY_FILE.read_text())
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
    return []

def compute_confidence(capsule):
    """
    Fallback confidence metric (used only when capsule has no explicit 'confidence'):
    - Verified: +40
    - Has timestamp: +30
    - Purpose is known: +20
    - Has key_items or entry_points: +10
    Max = 100
    """
    confidence = 0
    if capsule.get("verified", False):
        confidence += 40
    if capsule.get("timestamp"):
        confidence += 30
    if capsule.get("purpose") not in ["Unknown", ""]:
        confidence += 20
    if capsule.get("key_items") or capsule.get("entry_points"):
        confidence += 10
    return min(confidence, 100)

def get_confidence(capsule):
    conf = capsule.get("confidence", None)
    if conf is None:
        return compute_confidence(capsule)
    try:
        return int(conf)
    except (ValueError, TypeError):
        return compute_confidence(capsule)

def classify_capsules(memory):
    """
    Primary classification uses explicit 'status' if present.
    Fallback preserves previous behavior for older capsules.
    """
    completed, pending, queued, running, blocked, failed = [], [], [], [], [], []

    for cap in memory:
        status = (cap.get("status") or "").strip().lower()

        if status in ("done", "completed", "success", "succeeded"):
            completed.append(cap); continue
        if status in ("running", "in_progress"):
            running.append(cap); continue
        if status in ("blocked", "waiting"):
            blocked.append(cap); continue
        if status in ("failed", "error"):
            failed.append(cap); continue
        if status in ("queued",):
            queued.append(cap); continue
        if status in ("pending", "todo", ""):
            # fall through to default rules below
            pass

        # Fallback rules (legacy)
        if cap.get("verified") and cap.get("timestamp"):
            completed.append(cap)
        elif cap.get("purpose") in ["CurrentGoal:SubTasks", "MasterFirst"]:
            queued.append(cap)
        else:
            pending.append(cap)

    return completed, running, pending, blocked, failed, queued

def print_audit():
    memory = load_memory()
    completed, running, pending, blocked, failed, queued = classify_capsules(memory)

    print(f"=== Echo Audit Snapshot ===\nGenerated: {datetime.now()}\nTotal capsules: {len(memory)}\n")

    def print_capsules(title, capsules):
        print(f"--- {title} ---")
        for cap in capsules:
            conf = get_confidence(cap)
            print(
                f"{cap.get('purpose', 'Unknown')} | "
                f"ID: {cap.get('capsule_id', 'N/A')} | "
                f"Status: {cap.get('status', 'N/A')} | "
                f"Timestamp: {cap.get('timestamp', 'N/A')} | "
                f"Confidence: {conf}%"
            )
        print()

    print_capsules("Completed", completed)
    print_capsules("Running", running)
    print_capsules("Pending", pending)
    print_capsules("Blocked", blocked)
    print_capsules("Failed", failed)
    print_capsules("Queued Workflows/Commands", queued)

if __name__ == "__main__":
    print_audit()
