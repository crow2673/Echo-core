#!/usr/bin/env python3
import json
from pathlib import Path
import argparse
import sys

MEMORY_FILE = Path("echo_memory.json") # Consistent with original

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

def main():
    parser = argparse.ArgumentParser(description="Create a master command capsule for Echo.")
    parser.add_argument("--instruction", help="The primary instruction for the master command capsule.")
    args = parser.parse_args()

    print("Echo Command Intake — Phase 1 Master First Command")

    instruction = args.instruction if args.instruction is not None else input("Enter your instruction: ").strip()
    
    if not instruction:
        print("No instruction entered. Exiting.", file=sys.stderr)
        return

    memory = load_memory()
    
    # Define the automated arguments for workflow_intake.py
    # You can customize these as needed for your "MasterFirst" purpose
    workflow_intake_command = (
        "./workflow_intake.py "
        "--id 'AutomatedMasterTask' "
        "--purpose 'Automated intake for MasterFirst workflow processing' "
        "--sensitivity 'internal' "
        "--key-items 'master,workflow,automation' "
        "--entry-points 'execute,monitor'" # Example entry points for this capsule
    )

    # Create master command capsule
    capsule = {
        "capsule_id": "COMMAND:MasterFirst",
        "purpose": "Combine financial automation, income scanning, and workflow readiness (driven by: " + instruction + ")",
        "key_items": ["Outlier", "Hubstaff", "Echo", "Browser", "Terminal", "Financial", "Income"],
        # <--- KEY CHANGE HERE: Pass arguments directly in entry_points
        "entry_points": [
            "./echo.py", # Assuming this is not interactive or has its own non-interactive mode
            workflow_intake_command, # This will now be called with arguments
            "outlier-app", # Assuming these are external commands or aliases
            "hubstaff-app"
        ],
        "sensitivity": "internal",
        "tasks": [
            {"task": "Check and pay all upcoming bills automatically", "tool": "Echo", "status": "pending", "notes": ""},
            {"task": "Scan Outlier and other platforms for passive income opportunities", "tool": "Outlier", "status": "pending", "notes": ""},
            {"task": "Review and organize all active tasks in Echo memory, flag high-priority items", "tool": "Echo", "status": "pending", "notes": ""}
        ],
        "parent_root": "ROOT:Workspace",
        "instruction": instruction
    }
    
    # Append to memory
    memory.append(capsule)
    save_memory(memory)

    print("\nMaster First Command capsule created and stored in Echo memory.")
    print("Tasks ready for Phase 2 execution:")
    for i, t in enumerate(capsule["tasks"], start=1):
        print(f"{i}) {t['task']} [Tool: {t['tool']}] Status: {t['status']}")

if __name__ == "__main__":
    main()
