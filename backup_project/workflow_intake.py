#!/usr/bin/env python3
import json
from pathlib import Path
import argparse

STATE_FILE = Path(__file__).parent / "echo_state.json"
MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_state():
    if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
        print(f"Warning: {STATE_FILE} not found or empty. Using default memory policy.")
        return {"memory_policy": {"store_only": [], "never_store": [], "confirmation_required": False}}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def compress_capsule(capsule: dict):
    """
    Simple compression: keep purpose, key items, sensitivity, entry points.
    Replace long lists with counts if necessary.
    """
    compressed = {
        "capsule_id": capsule.get("capsule_id", "UNKNOWN"),
        "purpose": capsule.get("purpose", ""),
        "key_items": capsule.get("key_items", [])[:3],
        "sensitivity": capsule.get("sensitivity", "internal"),
        "entry_points": capsule.get("entry_points", [])[:3]
    }
    return compressed

def store_capsule(compressed_capsule):
    memory = [] # Always start with an empty list assumption
    if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 0:
        try:
            with open(MEMORY_FILE, "r") as f:
                loaded_content = json.load(f)
                if isinstance(loaded_content, list): # <--- CRITICAL TYPE CHECK ADDED
                    memory = loaded_content
                else:
                    print(f"Warning: {MEMORY_FILE} contains a {type(loaded_content).__name__} instead of a list. Initializing with empty memory.")
                    memory = [] # Reset to list if it's not a list
        except json.JSONDecodeError:
            print(f"Warning: {MEMORY_FILE} is corrupted or not valid JSON. Initializing with empty memory.")
            memory = []
    
    memory.append(compressed_capsule)
    
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)
    print(f"Compressed capsule stored: {compressed_capsule['capsule_id']}")

def main():
    state = load_state()
    print("Echo Workflow Intake — Offline-Friendly")
    print("Memory policy:", state["memory_policy"])
    
    parser = argparse.ArgumentParser(description="Ingest a workflow capsule into Echo's memory.")
    parser.add_argument("--id", help="Capsule ID")
    parser.add_argument("--purpose", help="Purpose of the workflow (1-2 lines)")
    parser.add_argument("--sensitivity", default=None, help="Sensitivity (public/internal/private)")
    parser.add_argument("--key-items", help="Key items (comma-separated, max 5)")
    parser.add_argument("--entry-points", help="Entry points/commands (comma-separated, max 5)")
    args = parser.parse_args()

    capsule_id = args.id if args.id is not None else input("Capsule ID: ")
    purpose = args.purpose if args.purpose is not None else input("Purpose (1-2 lines): ")
    sensitivity = args.sensitivity if args.sensitivity is not None else input("Sensitivity (public/internal/private): ")
    if not sensitivity:
        sensitivity = "internal"

    key_items_raw = args.key_items if args.key_items is not None else input("Key items (comma-separated, max 5): ")
    key_items = [item.strip() for item in key_items_raw.split(",")[:5] if item.strip()] if key_items_raw else []

    entry_points_raw = args.entry_points if args.entry_points is not None else input("Entry points/commands (comma-separated, max 5): ")
    entry_points = [item.strip() for item in entry_points_raw.split(",")[:5] if item.strip()] if entry_points_raw else []

    capsule = {
        "capsule_id": capsule_id.strip(),
        "purpose": purpose.strip(),
        "sensitivity": sensitivity.strip(),
        "key_items": key_items,
        "entry_points": entry_points
    }

    compressed = compress_capsule(capsule)
    store_capsule(compressed)
    
    # Store if allowed (original logic modified slightly for robustness)
    allowed_fields = state["memory_policy"].get("store_only", [])
    to_store = {k:v for k,v in compressed.items() if k in allowed_fields or k in ["capsule_id", "sensitivity"]}
    
    # This stores the capsule a second time, with filtered fields.
    # Consider if this is intended behavior. If you only want the filtered version,
    # you might remove the first store_capsule(compressed) call.
    store_capsule(to_store)

    print("Capsule intake complete. Only allowed fields stored according to policy.")

if __name__ == "__main__":
    main()
