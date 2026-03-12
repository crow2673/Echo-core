#!/usr/bin/env python3
"""
name: Echo Control Center
description: Unified GUI for Echo Launcher, Dashboard, and Command Center with real-time task updates and confidence bars
type: python
"""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
import subprocess
import json
import time
import glob
import os
import sys

# --- Paths ---
BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "echo_memory.json"
STATE_FILE = BASE_DIR / "echo_state.json" # Adding for robustness
SCRIPT_GLOB = BASE_DIR / "echo_*.py"
SCRIPT_SH_GLOB = BASE_DIR / "echo_*.sh"
LAUNCHER = BASE_DIR / "echo_launcher.py"
REFRESH_INTERVAL = 3000  # milliseconds

# --- Helpers ---
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
        except Exception as e:
            print(f"Warning: Could not read metadata from {s}: {e}", file=sys.stderr)
            pass # Continue if we can't read metadata
        metadata[s] = meta
    return metadata

def load_memory():
    memory = []
    if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 0:
        try:
            with open(MEMORY_FILE, "r") as f:
                loaded_content = json.load(f)
                if isinstance(loaded_content, list):
                    memory = loaded_content
                else:
                    print(f"Warning: {MEMORY_FILE} contains a {type(loaded_content).__name__} instead of a list. Initializing with empty memory.", file=sys.stderr)
                    memory = []
        except json.JSONDecodeError:
            print(f"Warning: {MEMORY_FILE} is corrupted or not valid JSON. Initializing with empty memory.", file=sys.stderr)
            memory = []
    return memory

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def run_script(path):
    if path:
        # Check if the path includes arguments
        parts = path.split(" ", 1) # Split only on the first space to separate script from args
        script_path = parts[0]
        script_args = parts[1:] # Remaining parts are arguments
        
        if script_path.endswith(".py"):
            subprocess.Popen([sys.executable, script_path] + script_args)
        else: # Assuming shell scripts or external commands
            subprocess.Popen(["bash", "-c", path]) # Use bash -c to execute the full command string
            
def run_all_pending():
    memory = load_memory()
    # <--- CRITICAL FIX: Convert confidence to int for comparison ---
    pending_tasks = []
    for c in memory:
        confidence_val = c.get("confidence")
        try:
            confidence_val = int(confidence_val) # Try converting to int
        except (ValueError, TypeError):
            confidence_val = 0 # Default to 0 if conversion fails or it's None
        
        if confidence_val < 50 or not c.get("timestamp"):
            pending_tasks.append(c)

    for task in pending_tasks:
        for ep in task.get("entry_points") or []:
            run_script(ep)
        task["confidence"] = 90
        task["timestamp"] = int(time.time())
    save_memory(memory) # Save memory after updating tasks
    refresh_dashboard()
    update_launcher_buttons()

# --- GUI Setup ---
root = tk.Tk()
root.title("Echo Control Center")
root.geometry("900x650")

notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True)

# --- Launcher Tab ---
launcher_tab = ttk.Frame(notebook)
notebook.add(launcher_tab, text="Launcher")

script_metadata = scan_scripts()
script_buttons = {}

def update_launcher_buttons():
    memory = load_memory()
    pending_capsules_paths = set() # Use a set to avoid duplicates
    for c in memory:
        # <--- CRITICAL FIX: Convert confidence to int for comparison ---
        confidence_val = c.get("confidence")
        try:
            confidence_val = int(confidence_val)
        except (ValueError, TypeError):
            confidence_val = 0
            
        eps = c.get("entry_points") or []
        if not eps:
            continue
        if confidence_val < 50 or not c.get("timestamp"):
            # We're interested in the *script path*, not the full command string for button coloring
            for ep_full_command in eps:
                pending_capsules_paths.add(ep_full_command.split(" ")[0]) # Get just the script path

    for meta in script_metadata.values():
        btn = script_buttons.get(meta["path"]) # Use .get for safety
        if btn:
            # Check if *any* entry point associated with this script (or the script itself) is pending
            is_pending = False
            for pending_path in pending_capsules_paths:
                if meta["path"] == pending_path:
                    is_pending = True
                    break
            
            if is_pending:
                btn.config(bg="red")
            else:
                btn.config(bg="green")
    root.after(REFRESH_INTERVAL, update_launcher_buttons)

# Create buttons for scripts
script_frame = ttk.Frame(launcher_tab)
script_frame.pack(pady=10)
for meta in script_metadata.values():
    btn = tk.Button(script_frame, text=meta["name"], width=40, command=lambda p=meta["path"]: run_script(p))
    btn.pack(pady=2)
    script_buttons[meta["path"]] = btn

run_all_button = tk.Button(launcher_tab, text="Run All Pending Workflows", command=run_all_pending)
run_all_button.pack(pady=10)


# --- Dashboard Tab ---
dashboard_tab = ttk.Frame(notebook)
notebook.add(dashboard_tab, text="Dashboard")

tasks_frame = ttk.Frame(dashboard_tab)
tasks_frame.pack(fill='both', expand=True, padx=10, pady=10)

def heartbeat_color(ts):
    # Determine color based on how recently the timestamp was updated
    # Green if within 1 minute, orange if within 5 minutes, red otherwise
    current_time = time.time()
    if current_time - ts < 60:
        return "green"
    elif current_time - ts < 300:
        return "orange"
    else:
        return "red"

def refresh_dashboard():
    for widget in tasks_frame.winfo_children():
        widget.destroy()
    memory = load_memory()
    
    # <--- CRITICAL FIX: Convert confidence to int for comparison ---
    pending_tasks = []
    for c in memory:
        confidence_val = c.get("confidence")
        try:
            confidence_val = int(confidence_val)
        except (ValueError, TypeError):
            confidence_val = 0
            
        if confidence_val < 50 or not c.get("timestamp"):
            pending_tasks.append(c)

    for idx, t in enumerate(pending_tasks):
        capsule_id = t.get("capsule_id", f"Task {idx}")
        # <--- CRITICAL FIX: Ensure confidence is int for display too if needed ---
        conf_raw = t.get("confidence", 0)
        try:
            conf = int(conf_raw)
        except (ValueError, TypeError):
            conf = 0 # Default to 0 if it's not a valid number

        ts = t.get("timestamp", int(time.time())) # Default to current time if no timestamp
        
        frame = tk.Frame(tasks_frame, relief="groove", borderwidth=2)
        frame.pack(fill="x", pady=1)

        # Labels for display
        tk.Label(frame, text=f"ID: {capsule_id}", anchor="w").pack(fill="x")
        tk.Label(frame, text=f"Purpose: {t.get('purpose', 'N/A')}", anchor="w").pack(fill="x")
        tk.Label(frame, text=f"Confidence: {conf}%", anchor="w").pack(fill="x")
        
        # Heartbeat indicator
        heartbeat_canvas = tk.Canvas(frame, width=20, height=20, bg=heartbeat_color(ts))
        heartbeat_canvas.create_oval(5, 5, 15, 15, fill="white", outline="") # Inner dot
        heartbeat_canvas.pack(side="right", padx=5)

        # Run button for individual tasks (if an entry point exists)
        ep = (t.get("entry_points") or [None])[0]
        if ep: # Only show button if there's an entry point
            btn = tk.Button(frame, text="Run", command=lambda p=ep: run_script(p))
            btn.pack(side="right", padx=5)
        
    root.after(REFRESH_INTERVAL, refresh_dashboard)


# --- Initial Calls ---
refresh_dashboard()
update_launcher_buttons() # Starts the auto-update loop for launcher buttons

root.mainloop()
