#!/usr/bin/env python3
"""
core/auto_act.py
================
Echo's autonomous execution engine.

Echo reads her own income/build suggestions from feedback_log.json,
decides which ones to act on, executes them within safe boundaries,
and logs what she did.

Boundaries:
- SAFE: restart services, write new files to core/, notify, log
- NOTIFY: modify existing core files
- NEVER: outside ~/Echo/, delete, move GLM, modify soul document
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import sys, os; sys.path.insert(0, os.path.expanduser("~/Echo/core")); from regret_index import log_action, get_flags

BASE = Path.home() / "Echo"
FEEDBACK_LOG = BASE / "memory/feedback_log.json"
ACTION_LOG = BASE / "logs/auto_act.log"
NOTIFY = BASE / "core/notifier.py"

SAFE_ACTIONS = ["restart_service", "write_new_file", "append_log", "notify", "adjust_golem_pricing"]
NOTIFY_ACTIONS = ["modify_existing_file", "install_package"]
NEVER_ACTIONS = ["delete", "move_glm", "modify_soul", "outside_echo"]

PROTECTED_FILES = [
    "echo_core_daemon.py",
    "echo_memory_sqlite.py", 
    "Echo.Modelfile",
    "echo_contract.json"
]

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} — {msg}"
    print(line)
    with open(ACTION_LOG, "a") as f:
        f.write(line + "\n")

def notify_phone(msg):
    subprocess.run(["python3", str(NOTIFY), msg], capture_output=True)

def load_pending_suggestions():
    if not FEEDBACK_LOG.exists():
        return []
    data = json.loads(FEEDBACK_LOG.read_text())
    return [s for s in data if s.get("status") == "pending"]

def is_safe_target(filepath):
    """Check file is inside Echo and not protected."""
    try:
        target = (BASE / filepath).resolve()
        if not str(target).startswith(str(BASE)):
            return False, "outside Echo directory"
        for protected in PROTECTED_FILES:
            if target.name == protected:
                return False, f"protected file: {protected}"
        return True, "ok"
    except Exception as e:
        return False, str(e)

def execute_suggestion(suggestion):
    """
    Try to execute a suggestion autonomously.
    Returns (success, action_taken, notes)
    """
    text = suggestion.get("suggestion", "").lower()
    sid = suggestion.get("id", "unknown")
    # Log to regret index before acting
    entry_id = log_action(
        action_id=sid,
        category="auto_act",
        description=suggestion.get("suggestion", ""),
        context="auto_act"
    )
    suggestion["regret_entry_id"] = entry_id

    # Restart service
    if "restart" in text and "service" in text:
        for svc in ["echo-core", "golem-provider", "yagna", "echo-wake"]:
            if svc in text:
                result = subprocess.run(
                    ["systemctl", "--user", "restart", f"{svc}.service"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    # Verify: check it's actually running now
                    import time; time.sleep(2)
                    verify = subprocess.run(
                        ["systemctl", "--user", "is-active", f"{svc}.service"],
                        capture_output=True, text=True
                    )
                    if verify.stdout.strip() in ("active", "activating"):
                        return True, f"restarted {svc}.service", "verified active"
                    else:
                        return False, f"restarted {svc} but verify failed", verify.stdout.strip()
                else:
                    return False, f"failed to restart {svc}", result.stderr

    # Write a new utility file
    if "write" in text and ("script" in text or "utility" in text or "tool" in text):
        from core.self_coder import write_code, test_code
        # Extract what to write from suggestion
        fname = f"auto_{sid[:8]}.py"
        safe, reason = is_safe_target(f"core/{fname}")
        if not safe:
            return False, "write blocked", reason
        success = write_code(
            task_description=suggestion.get("suggestion", ""),
            output_path=f"core/{fname}",
            context=f"Auto-executed suggestion ID: {sid}"
        )
        if success and test_code(f"core/{fname}"):
            return True, f"wrote and verified core/{fname}", "self-coded"
        return False, "write failed or syntax error", ""

    # Golem task queue check
    if "golem" in text and ("task" in text or "queue" in text or "income" in text or "tasks=0" in text):
        result = subprocess.run(
            ["bash", "-lc", "ya-provider task list 2>/dev/null | head -20 || golemsp status 2>/dev/null | head -10"],
            capture_output=True, text=True
        )
        output = result.stdout.strip() or "no task output"
        # Log to golem recommendations
        with open(BASE / "logs/golem_recommendations.log", "a") as f:
            from datetime import datetime
            f.write(f"{datetime.now()} — auto_act check: {output[:200]}\n")
        # Observation only — not a success, score 0
        suggestion["_score_override"] = 0
        return True, "checked Golem task queue", output[:150]

    # Adjust Golem pricing
    if "golem" in text and ("price" in text or "pricing" in text or "cpu" in text):
        result = subprocess.run(
            ["bash", "-lc", "golemsp status 2>/dev/null | head -5"],
            capture_output=True, text=True
        )
        suggestion["_score_override"] = 0
        return True, "checked Golem status for pricing context", result.stdout[:200]

    # Check and log system status
    if "system" in text and ("status" in text or "check" in text or "health" in text):
        result = subprocess.run(
            ["bash", "-lc", "systemctl --user is-active echo-core golem-provider yagna"],
            capture_output=True, text=True
        )
        suggestion["_score_override"] = 0
        return True, "ran system health check", result.stdout.strip()

    # Fix/patch an existing Python file
    if "fix_python_file" in text or ("fix" in text and ".py" in text and "self_coder" not in text):
        from core.self_coder import fix_file, test_code
        import re
        # Extract file path from suggestion
        match = re.search(r'core/[\w_]+\.py', suggestion.get("suggestion", ""))
        if not match:
            return False, "fix blocked", "could not extract file path from suggestion"
        file_path = match.group(0)
        fix_desc = suggestion.get("suggestion", "")
        safe, reason = is_safe_target(file_path)
        if not safe:
            return False, "fix blocked", reason
        success = fix_file(file_path, fix_desc)
        if success and test_code(file_path):
            return True, f"fixed and verified {file_path}", "self-fixed"
        return False, "fix failed or syntax error", ""

    return False, "no executable action matched", text[:100]

def mark_suggestion(data, sid, status, notes):
    for s in data:
        if s.get("id") == sid:
            s["status"] = status
            s["acted_at"] = datetime.now().isoformat()
            s["action_notes"] = notes
    return data

def run():
    import fcntl
    lockfile = open(BASE / "logs/auto_act.lock", "w")
    try:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("auto_act already running, skipping")
        return
    log("auto_act started")
    # Check regret flags — skip flagged action types
    active_flags = get_flags()
    flagged_categories = {f[1] for f in active_flags if f[0] == "category"}
    flagged_actions = {f[1] for f in active_flags if f[0] == "action"}
    if active_flags:
        log(f"regret flags active: {len(active_flags)} — {[f[1] for f in active_flags]}")
    pending = load_pending_suggestions()
    
    if not pending:
        log("no pending suggestions")
        return

    log(f"{len(pending)} pending suggestions")
    data = json.loads(FEEDBACK_LOG.read_text())
    acted = 0

    for suggestion in pending[:3]:  # max 3 per cycle
        sid = suggestion.get("id", "unknown")
        text = suggestion.get("suggestion", "")[:80]
        log(f"evaluating: [{sid}] {text}")

        # Skip if category or action is flagged by regret index
        if suggestion.get("category") in flagged_categories:
            log(f"SKIPPED (regret flag — category): {sid}")
            data = mark_suggestion(data, sid, "skipped", "regret index: category flagged")
            continue
        if sid in flagged_actions:
            log(f"SKIPPED (regret flag — action): {sid}")
            data = mark_suggestion(data, sid, "skipped", "regret index: action flagged")
            continue
        success, action, notes = execute_suggestion(suggestion)

        if success:
            log(f"EXECUTED: {action} — {notes}")
            notify_phone(f"Echo acted: {action}")
            data = mark_suggestion(data, sid, "acted_on", f"{action}: {notes}")
            acted += 1
            if suggestion.get("regret_entry_id"):
                from core.regret_index import update_outcome
                score = suggestion.get("_score_override", 1)
                update_outcome(suggestion["regret_entry_id"], score=score, notes=f"success: {action}")
        else:
            log(f"SKIPPED: {action} — {notes}")
            data = mark_suggestion(data, sid, "skipped", f"{action}: {notes}")
            if suggestion.get("regret_entry_id"):
                from core.regret_index import update_outcome
                update_outcome(suggestion["regret_entry_id"], score=-1, notes=f"failed: {action}")

    FEEDBACK_LOG.write_text(json.dumps(data, indent=2))
    log(f"cycle complete — acted on {acted}/{len(pending[:3])} suggestions")

    # Update changelog
    with open(BASE / "CHANGELOG.md", "a") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Auto-Act Cycle\n")
        f.write(f"- Evaluated {len(pending[:3])} suggestions, acted on {acted}\n")

if __name__ == "__main__":
    run()
