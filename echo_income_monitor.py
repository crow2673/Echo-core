import json
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")

def report():
    if not MEMORY_FILE.exists(): return
    memory = json.loads(MEMORY_FILE.read_text())
    
    print("--- Echo Income Dashboard ---")
    total_potential = 0
    
    for cap in memory:
        if cap.get("capsule_id", "").startswith("INCOME:"):
            name = cap["capsule_id"].split(":")[1]
            status = cap["status"]
            pay = cap.get("expected_pay", "0")
            print(f"Source: {name:15} | Status: {status:10} | Potential: {pay}")
            
    # Also check Outlier (Task 2)
    for cap in memory:
        if cap.get("capsule_id") == "TASK:MasterFirst:2":
            print(f"Source: OUTLIER        | Status: {cap['status']:10} | Real-Time: Check Browser")

if __name__ == "__main__":
    report()
