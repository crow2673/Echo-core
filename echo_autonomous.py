#!/usr/bin/env python3
import json
import time
import re
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")

def main():
    print("--- Echo Autonomous Engine: Smart Financial Mode ---")
    while True:
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r") as f:
                    memory = json.load(f)
                
                all_found_values = []
                for cap in memory:
                    notes = cap.get("result_notes", [])
                    for note in notes:
                        # Extract value: works for "$888.88" or "888.88"
                        match = re.search(r"Power\s?\$?([0-9,.]+)", note)
                        if match:
                            val = float(match.group(1).replace(',', ''))
                            all_found_values.append(val)
                
                # Take the very last value found (the most recent update)
                latest_bp = all_found_values[-1] if all_found_values else 0.0
                
                print(f"[{time.strftime('%H:%M:%S')}] Monitoring... BP: ${latest_bp:.2f}")
            except Exception as e:
                pass # Silent during updates
        
        time.sleep(10)

if __name__ == "__main__":
    main()
