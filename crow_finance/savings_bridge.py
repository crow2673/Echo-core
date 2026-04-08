import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("./data")
SAVINGS_PATH = DATA_DIR / "savings.json"
HISTORY_PATH = DATA_DIR / "account_history.jsonl"


def read_savings():
    if not SAVINGS_PATH.exists():
        return []
    try:
        return json.loads(SAVINGS_PATH.read_text())
    except:
        return []


def append_savings_to_history():
    savings_accounts = read_savings()
    if not savings_accounts:
        return {"ok": False, "reason": "no savings accounts"}

    timestamp = datetime.utcnow().isoformat()

    history_entry = {
        "timestamp": timestamp,
        "accounts": []
    }

    for s in savings_accounts:
        history_entry["accounts"].append({
            "account_id": f"savings_{s.get('name','unknown')}",
            "name": s.get("name", "Savings"),
            "type": "savings",
            "subtype": "manual",
            "balance": float(s.get("balance", 0))
        })

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(history_entry) + "\n")

    return {"ok": True, "added": len(history_entry["accounts"])}
