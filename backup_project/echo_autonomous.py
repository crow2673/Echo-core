#!/usr/bin/env python3
import json
from pathlib import Path
import time

MEMORY_FILE = Path("echo_memory.json")
AUTONOMOUS_DELAY = 5  # seconds between task cycles

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def execute_task(task):
    tool = task.get("tool", "")
    name = task.get("task", "")
    status = task.get("status", "pending")
    sensitive = task.get("sensitive", False)
    
    if status == "completed":
        return task  # skip already done tasks
    
    if sensitive:
        confirm = input(f"Task '{name}' is sensitive. Execute? (y/n): ").strip().lower()
        if confirm != "y":
            task["status"] = "pending"
            return task
    
    print(f"Executing '{name}' using {tool}...")
    
    try:
        # Simulated execution
        time.sleep(1)
        task["status"] = "completed"
        task["last_executed"] = time.strftime("%Y-%m-%d %H:%M:%S")
        task["notes"] = "Executed successfully."
    except Exception as e:
        task["status"] = "failed"
        task["notes"] = str(e)
    
    return task

def main_loop():
    print("Echo Autonomous Mode — Phase 2 Active (Safe Mode)")
    while True:
        memory = load_memory()
        tasks_found = False
        
        for capsule in memory:
            # Only process capsules explicitly marked for autonomous Phase 2
            if capsule.get("autonomous_ready") or capsule.get("phase") == "active":
                if "tasks" in capsule:
                    for i, task in enumerate(capsule["tasks"]):
                        if task.get("status") != "completed":
                            tasks_found = True
                            capsule["tasks"][i] = execute_task(task)
        
        save_memory(memory)
        
        if not tasks_found:
            print(f"[{time.strftime('%H:%M:%S')}] No pending tasks. Heartbeat active.")
        
        time.sleep(AUTONOMOUS_DELAY)

if __name__ == "__main__":
    main_loop()
