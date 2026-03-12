#!/usr/bin/env python3
import json
from pathlib import Path
import argparse

MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_memory():
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
    return memory

def store_capsule(capsule):
    memory = load_memory()
    memory.append(capsule)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)
    print(f"Root capsule stored: {capsule['capsule_id']}")

def main():
    print("Echo Root Workspace Intake — Offline-Friendly")

    parser = argparse.ArgumentParser(description="Ingest a root workspace capsule into Echo's memory.")
    parser.add_argument("--id", help="Capsule ID")
    parser.add_argument("--scope", help="Scope (what directories are included/excluded)")
    parser.add_argument("--locations", help="Location/Label (comma-separated paths)")
    parser.add_argument("--purpose", help="Purpose of the workspace (1-2 lines)")
    parser.add_argument("--sensitivity", default=None, help="Sensitivity (public/internal/private)")
    parser.add_argument("--size-scale", help="Size/Scale (approx #projects, datasets, or size)")
    parser.add_argument("--key-items", help="Key items (comma-separated, max 5)")
    parser.add_argument("--entry-points", help="Entry points/commands (comma-separated, max 5)")
    parser.add_argument("--notes", help="Notes / gotchas (optional, 1-3 bullets, comma-separated)")
    args = parser.parse_args()

    capsule_id = args.id if args.id is not None else input("Capsule ID: ")
    scope = args.scope if args.scope is not None else input("Scope (what directories are included/excluded): ")
    
    locations_raw = args.locations if args.locations is not None else input("Location/Label (comma-separated paths): ")
    locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()] if locations_raw else []

    purpose = args.purpose if args.purpose is not None else input("Purpose (1-2 lines): ")
    
    sensitivity = args.sensitivity if args.sensitivity is not None else input("Sensitivity (public/internal/private): ")
    if not sensitivity:
        sensitivity = "internal"

    size_scale = args.size_scale if args.size_scale is not None else input("Size/Scale (approx #projects, datasets, or size): ")
    
    key_items_raw = args.key_items if args.key_items is not None else input("Key items (comma-separated, max 5): ")
    key_items = [item.strip() for item in key_items_raw.split(",")[:5] if item.strip()] if key_items_raw else []

    entry_points_raw = args.entry_points if args.entry_points is not None else input("Entry points/commands (comma-separated, max 5): ")
    entry_points = [item.strip() for item in entry_points_raw.split(",")[:5] if item.strip()] if entry_points_raw else []

    notes_raw = args.notes if args.notes is not None else input("Notes / gotchas (optional, 1-3 bullets, comma-separated): ")
    notes = [note.strip() for note in notes_raw.split(",")[:3] if note.strip()] if notes_raw else []

    capsule = {
        "capsule_id": capsule_id.strip(),
        "scope": scope.strip(),
        "locations": locations,
        "purpose": purpose.strip(),
        "sensitivity": sensitivity.strip(),
        "size_scale": size_scale.strip(),
        "key_items": key_items,
        "entry_points": entry_points,
        "notes": notes
    }

    store_capsule(capsule)
    print("Root capsule intake complete.")
    
if __name__ == "__main__":
    main()
