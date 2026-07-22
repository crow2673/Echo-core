#!/usr/bin/env python3
"""core/telegram_approver.py — Applies explicit draft approval decisions.

Reads content/pending_approval.json. On YES: publishes the draft immediately.
On NO: discards the draft and marks the topic rejected.
Telegram polling is owned exclusively by telegram_intake.py.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APPROVAL_FILE = BASE / "content/pending_approval.json"
STRATEGY_FILE = BASE / "memory/content_strategy.json"
LOG = BASE / "logs/telegram_approver.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def save_approval(state: dict):
    tmp = APPROVAL_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(APPROVAL_FILE)


def mark_topic(topic_id: str, status: str):
    if not STRATEGY_FILE.exists():
        return
    strategy = json.loads(STRATEGY_FILE.read_text())
    for item in strategy.get("queue", []):
        if item.get("id") == topic_id or item.get("title") == topic_id:
            item["status"] = status
            break
    tmp = STRATEGY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(strategy, indent=2))
    tmp.rename(STRATEGY_FILE)


def notify(title: str, msg: str):
    try:
        from core.notifier import notify as _notify
        _notify(title, msg)
    except Exception:
        pass


def publish_draft(draft_file: str) -> bool:
    publisher = BASE / "echo_devto_publisher.py"
    try:
        result = subprocess.run(
            [sys.executable, str(publisher), "--from-draft", draft_file],
            cwd=str(BASE),
            timeout=120,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            log(f"devto publish succeeded: {result.stdout.strip()[-100:]}")
            return True
        else:
            log(f"devto publish failed (exit {result.returncode}): {result.stderr.strip()[-200:]}")
            return False
    except Exception as e:
        log(f"devto publish error: {e}")
        return False


def publish_to_medium(draft_file: str) -> str | None:
    publisher = BASE / "tools/medium_publisher.py"
    try:
        result = subprocess.run(
            [sys.executable, str(publisher), "--from-draft", draft_file],
            cwd=str(BASE),
            timeout=300,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("[medium] published:"):
                return line.split("published:", 1)[1].strip()
        if result.returncode != 0:
            log(f"medium publish failed: {result.stderr.strip()[-200:]}")
        return None
    except Exception as e:
        log(f"medium publish error: {e}")
        return None


def handle_answer(answer: str) -> bool:
    """Apply an explicit yes/no answer already consumed by telegram_intake."""
    if not APPROVAL_FILE.exists():
        log("no pending approval — nothing to do")
        return False

    state = json.loads(APPROVAL_FILE.read_text())
    if state.get("status") != "awaiting_approval":
        log(f"approval status is '{state.get('status')}' — skipping")
        return False

    normalized = answer.strip().lower()
    if normalized in ("yes", "y", "publish"):
        answer = "yes"
    elif normalized in ("no", "n", "discard", "reject", "skip"):
        answer = "no"
    else:
        return False

    draft_file = state.get("draft_file", "")
    topic_id = state.get("topic_id", "")
    title = state.get("title", "")

    if answer == "yes":
        log(f"YES received — publishing: {title[:60]}")
        devto_ok = publish_draft(draft_file)
        medium_url = publish_to_medium(draft_file)

        if devto_ok or medium_url:
            mark_topic(topic_id, "published")
            state["status"] = "published"
            save_approval(state)
            platforms = []
            if devto_ok:
                platforms.append("Dev.to")
            if medium_url:
                platforms.append(f"Medium ({medium_url})")
            notify(
                "Published",
                f'"{title}" → {" + ".join(platforms)}',
            )
        else:
            notify("Publish failed", f'Both Dev.to and Medium failed for: "{title}"')
            state["status"] = "publish_failed"
            save_approval(state)

    elif answer == "no":
        log(f"NO received — discarding: {title[:60]}")
        draft_path = Path(draft_file)
        if draft_path.exists():
            draft_path.unlink()
        mark_topic(topic_id, "rejected")
        state["status"] = "rejected"
        save_approval(state)
        notify("Draft discarded", f'"{title}" rejected — topic moved to rejected in queue.')
    return True


def run():
    """Timer compatibility: report pending state, but never poll or auto-approve."""
    if not APPROVAL_FILE.exists():
        log("no pending approval — nothing to do")
        return
    state = json.loads(APPROVAL_FILE.read_text())
    log(f"approval status is '{state.get('status')}' — waiting for telegram_intake")


if __name__ == "__main__":
    run()
