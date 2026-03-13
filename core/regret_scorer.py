#!/usr/bin/env python3
"""
Regret scorer — retroactively scores unscored regret entries
and wires future governor feedback into outcome_score.

Scoring logic:
- File creation tasks: check if file exists
- Service tasks: check if service is running  
- Script/fix tasks: check if file exists and is valid python
- Content/article tasks: score 0.5 (unknown, but not failure)
- Default unknown: score 0.3 (partial credit — at least it tried)
"""
import sqlite3, json, subprocess, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "memory/echo_events.db"
LOG = BASE / "logs/regret_scorer.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def service_running(name):
    try:
        r = subprocess.run(["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5)
        return r.stdout.strip() == "active"
    except Exception:
        return False

def score_entry(entry_id, description, data):
    desc = description.lower()
    score = None
    reason = ""

    # Service restart tasks
    if "restart" in desc and "service" in desc:
        # Extract service name
        for word in desc.split():
            if "echo-" in word or word.endswith(".service"):
                svc = word.strip(".,")
                running = service_running(svc)
                score = 1.0 if running else 0.2
                reason = f"service {svc} {'running' if running else 'not running'}"
                break
        if score is None:
            score = 0.5
            reason = "service task — current state unknown"

    # File creation / fix tasks
    elif any(x in desc for x in ["write a", "create", "fix ", "fix_python", "build "]):
        # Try to find a filename in the description
        for word in desc.split():
            word = word.strip(".,:'\"")
            if word.endswith(".py") or word.endswith(".json") or word.endswith(".md"):
                path = BASE / word
                if not path.exists():
                    path = BASE / "core" / word
                if path.exists():
                    score = 1.0
                    reason = f"file exists: {word}"
                else:
                    score = 0.1
                    reason = f"file not found: {word}"
                break
        if score is None:
            score = 0.4
            reason = "file task — could not verify"

    # Article / content tasks
    elif any(x in desc for x in ["article", "write more", "content", "publish"]):
        score = 0.5
        reason = "content task — outcome not measurable retroactively"

    # Analytics / monitoring tasks
    elif any(x in desc for x in ["analytics", "monitor", "check", "best performing"]):
        score = 0.6
        reason = "observation task — assumed completed"

    # Default
    else:
        score = 0.3
        reason = "unknown task type — minimal credit"

    return score, reason

def run():
    log("regret_scorer started")
    con = sqlite3.connect(DB)

    rows = con.execute(
        "SELECT id, data FROM events WHERE event_type='regret' AND outcome_score IS NULL"
    ).fetchall()

    log(f"found {len(rows)} unscored regret entries")
    scored = 0

    for row_id, data_json in rows:
        try:
            data = json.loads(data_json) if data_json else {}
            description = data.get("description", "")
            entry_id = data.get("entry_id", str(row_id))

            score, reason = score_entry(entry_id, description, data)

            # Update DB
            con.execute(
                "UPDATE events SET outcome_score=? WHERE id=?",
                (score, row_id)
            )
            # Update JSON data too
            data["score"] = score
            data["outcome_known"] = True
            data["outcome_notes"] = reason
            data["updated"] = datetime.now().isoformat()
            con.execute(
                "UPDATE events SET data=? WHERE id=?",
                (json.dumps(data), row_id)
            )
            log(f"  [{row_id}] score={score} — {reason[:60]}")
            scored += 1
        except Exception as e:
            log(f"  [{row_id}] ERROR: {e}")

    con.commit()
    con.close()

    log(f"scored {scored}/{len(rows)} entries")

    # Log to event ledger
    try:
        sys.path.insert(0, str(BASE))
        from core.event_ledger import log_event
        log_event("feedback", "regret_scorer",
            f"retroactively scored {scored} regret entries",
            score=1.0)
    except Exception:
        pass

if __name__ == "__main__":
    run()
