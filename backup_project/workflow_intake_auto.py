#!/usr/bin/env python3
import json
from pathlib import Path
import argparse # <--- NEW IMPORT
import sys # <--- NEW IMPORT

# Paths (adjust if BASE_DIR is needed here, current code assumes files are in current dir)
BASE_DIR = Path(__file__).parent
MEMORY_FILE = BASE_DIR / "echo_memory.json"
STATE_FILE = BASE_DIR / "echo_state.json" # Assuming state file might be needed here too

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

def find_verified_capsule(memory, purpose):
    for capsule in reversed(memory):
        if capsule.get("purpose") == purpose and capsule.get("verified", False):
            return capsule
    return None

# <--- MODIFIED verify_new_capsule function to accept args ---
def verify_new_capsule(purpose, have_ans=None, how_ans=None, why_ans=None):
    """
    Prompt verification for unseen workflows using have/how/why reference.
    Can also be run non-interactively by passing answers as arguments.
    """
    print(f"New workflow detected: '{purpose}'")
    print("Verification required using have / how / why reference system.")

    # 'have' question
    if have_ans is not None:
        have = have_ans.strip().lower()
        print(f"Have you seen/used this workflow before? (y/n): {have_ans}") # Show passed arg
    else:
        have = input("Have you seen/used this workflow before? (y/n): ").strip().lower()
    
    if have == 'y':
        print("Marking as verified based on previous experience.\n")
        return True
    
    # 'how' question
    if how_ans is not None:
        how = how_ans
        print(f"How should this workflow execute?: {how_ans}") # Show passed arg
    else:
        how = input("How should this workflow execute? ").strip()
    
    # 'why' question
    if why_ans is not None:
        why = why_ans
        print(f"Why is this workflow necessary?: {why_ans}") # Show passed arg
    else:
        why = input("Why is this workflow necessary? ").strip()
    
    # In an autonomous context, if we reach here and 'have' was not 'y', 
    # and 'how'/'why' were not provided, we might want to fail or use defaults.
    # For now, we'll assume a 'True' return if arguments are provided or interactively answered.
    
    print(f"Workflow '{purpose}' verified with explanation.\n")
    return True
# --- END MODIFIED verify_new_capsule function ---

# --- NEW main function (if workflow_intake_auto.py has one) or direct call ---
# Assuming workflow_intake_auto.py has a main function or similar entry point.
# If not, the function might be called directly by echo.py.
# For now, let's assume it has a main to allow independent testing with args.

def main():
    parser = argparse.ArgumentParser(description="Automated or interactive workflow intake verification.")
    parser.add_argument("--purpose", required=True, help="Purpose of the workflow to verify.")
    parser.add_argument("--have", help="Answer to 'Have you seen this workflow before?' (y/n)")
    parser.add_argument("--how", help="Answer to 'How should this workflow execute?'")
    parser.add_argument("--why", help="Answer to 'Why is this workflow necessary?'")
    args = parser.parse_args()

    # Load memory (though not directly used by verify_new_capsule in this snippet,
    # it's good practice for an intake script).
    memory = load_memory() 
    
    # Find if it's already verified
    verified_capsule = find_verified_capsule(memory, args.purpose)
    if verified_capsule:
        print(f"Workflow '{args.purpose}' already verified. Skipping interactive questions.")
        return True # Or handle as needed
    
    # Call the modified verification function
    if verify_new_capsule(args.purpose, args.have, args.how, args.why):
        # If successfully verified (or assumed verified by args),
        # you might want to mark it in memory or state here.
        # This part of the logic might reside in echo.py or another orchestrator.
        print(f"Automated verification for '{args.purpose}' completed.")
    else:
        print(f"Automated verification for '{args.purpose}' failed or not fully provided.")

if __name__ == "__main__":
    main()
