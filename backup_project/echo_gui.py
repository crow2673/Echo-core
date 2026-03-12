#!/usr/bin/env python3
"""
name: Echo Dashboard
description: Minimal GUI to monitor Echo heartbeat and pending tasks
type: python
"""

import json
import tkinter as tk
from pathlib import Path
import subprocess
import time

# --- Paths ---
BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "echo_memory.json"
LAUNCHER = BASE_DIR / "echo_launcher.py"

REFRESH_INTERVAL = 3000  # milliseconds

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return []

def heartbeat_color(last_update_ts):
    if time.time() - last_update_ts < 10:
        return "green"
    return "red"

def run_all_pending():
    subprocess.Popen(["python3", str(LAUNCHER), "runall"])

def run_task(script_path):
    subprocess.Popen(["python3", script_path])

# --- GUI ---
root = tk.Tk()
root.title("Echo Dashboard")

heartbeat_label = tk.Label(root, text="Heartbeat: Unknown", font=("Arial", 14))
heartbeat_label.pack(pady=10)

pending_label = tk.Label(root, text="Pending Tasks: 0", font=("Arial", 14))
pending_label.pack(pady=5)

tasks_listbox = tk.Listbox(root, width=80, height=15)
tasks_listbox.pack(pady=5)

run_all_button = tk.Button(root, text="Run All Pending Tasks", command=run_all_pending)
run_all_button.pack(pady=10)

def refresh():
    memory = load_memory()
    pending_tasks = [c for c in memory if c.get("confidence", 100) < 50 or not c.get("timestamp")]
    tasks_listbox.delete(0, tk.END)
    for t in pending_tasks:
        conf = t.get("confidence", "N/A")
        color = "red" if conf < 50 else "green"
        tasks_listbox.insert(tk.END, f"{t.get('capsule_id')} | Confidence: {conf}")
        tasks_listbox.itemconfig(tk.END, fg=color)
    # Heartbeat from last executed task timestamp
    if pending_tasks:
        last_ts = max([t.get("timestamp", 0) for t in pending_tasks])
        heartbeat_label.config(text=f"Heartbeat: {time.ctime(last_ts)}", fg=heartbeat_color(last_ts))
    else:
        heartbeat_label.config(text="Heartbeat: N/A", fg="green")
    pending_label.config(text=f"Pending Tasks: {len(pending_tasks)}")
    root.after(REFRESH_INTERVAL, refresh)

def on_double_click(event):
    selection = tasks_listbox.curselection()
    if selection:
        index = selection[0]
        memory = load_memory()
        pending_tasks = [c for c in memory if c.get("confidence", 100) < 50 or not c.get("timestamp")]
        task = pending_tasks[index]
        run_task(task.get("entry_points", [None])[0])

tasks_listbox.bind("<Double-Button-1>", on_double_click)
refresh()
root.mainloop()
