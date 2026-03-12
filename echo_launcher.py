#!/usr/bin/env python3
"""
name: Echo Launcher
description: Unified launcher for Echo scripts and commands
type: python
"""

import glob
import subprocess
import os
import sys
import json
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent
SCRIPT_GLOB = BASE_DIR / "echo_*.py"
SCRIPT_SH_GLOB = BASE_DIR / "echo_*.sh"
MANIFEST_FILE = BASE_DIR / "echo_manifest.json"
MEMORY_FILE = BASE_DIR / "echo_memory.json"

# --- Scan scripts ---
def scan_scripts():
    scripts = glob.glob(str(SCRIPT_GLOB)) + glob.glob(str(SCRIPT_SH_GLOB))
    metadata = {}
    for s in scripts:
        meta = {"path": s, "name": os.path.basename(s), "type": "python" if s.endswith(".py") else "shell"}
        try:
            with open(s) as f:
                for _ in range(5):
                    line = f.readline().strip()
                    if line.startswith("name:"):
                        meta["name"] = line.split("name:")[1].strip()
                        break
        except Exception:
            pass
        metadata[s] = meta
    return metadata

def save_manifest(metadata):
    with open(MANIFEST_FILE, "w") as f:
        json.dump({os.path.basename(k): v for k, v in metadata.items()}, f, indent=2)

# --- Run a script ---
def run_script(path):
    if path.endswith(".py"):
        subprocess.Popen([sys.executable, path])
    else:
        subprocess.Popen(["bash", path])

# --- Memory helpers ---
def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return []

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

# --- Run all pending tasks ---
def run_all_pending_tasks():
    memory = load_memory()
    pending_tasks = [c for c in memory if c.get("confidence", 100) < 50 or not c.get("timestamp")]
    if not pending_tasks:
        print("No pending tasks to run.")
        return
    for task in pending_tasks:
        script_path = task.get("entry_points", [])
        if script_path:
            for sp in script_path:
                print(f"Executing {sp} for task {task.get('capsule_id')}")
                run_script(sp)
        # Update confidence and timestamp after triggering
        task["confidence"] = 90
        task["timestamp"] = int(__import__("time").time())
    save_memory(memory)
    print(f"Executed {len(pending_tasks)} pending tasks.")

# --- CLI Mode ---
def cli_mode(metadata):
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd:
        if cmd == "runall":
            run_all_pending_tasks()
            return
        for meta in metadata.values():
            key = os.path.basename(meta["path"]).split("_")[-1].split(".")[0]
            if cmd == key:
                run_script(meta["path"])
                return
        print(f"Unknown command: {cmd}")
        print("Available commands:")
        for meta in metadata.values():
            print(f"  {os.path.basename(meta['path']).split('_')[-1].split('.')[0]}")
    else:
        print("No command provided. Available commands:")
        for meta in metadata.values():
            print(f"  {os.path.basename(meta['path']).split('_')[-1].split('.')[0]}")

# --- Main ---
def main():
    metadata = scan_scripts()
    save_manifest(metadata)
    cli_mode(metadata)

if __name__ == "__main__":
    main()
