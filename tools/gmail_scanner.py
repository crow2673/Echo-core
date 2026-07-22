#!/usr/bin/env python3
"""tools/gmail_scanner.py — scans Gmail for Alpaca fills, Fiverr orders, important alerts.
Runs every 30 minutes via echo-gmail-scanner.timer.
"""
import imaplib
import email
import json
import socket
from datetime import datetime, date
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/gmail_scanner.log"
STATE_FILE = BASE / "memory/gmail_scanner_state.json"

KEYWORDS = {
    "fiverr": ["fiverr", "order", "new message", "buyer"],
    "alpaca": ["alpaca", "order filled", "position", "trade"],
    "alert": ["alert", "warning", "critical", "failed"],
}
SUBJECT_TRIGGERS = ["order filled", "fiverr", "alpaca", "echo backup"]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_env():
    env = {}
    env_file = Path.home() / ".config/echo/golem.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_uid": 0, "scanned_at": ""}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)


def scan_gmail(user, password):
    alerts = []
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(30)
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        mail.login(user, password)
        mail.select("INBOX")

        state = load_state()
        last_uid = state.get("last_uid", 0)

        # Search today's unseen messages
        today = date.today().strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{today}" UNSEEN)')
        uids = data[0].split()

        new_max_uid = last_uid
        found = 0

        for uid in uids[-20:]:  # max 20 per run
            uid_int = int(uid)
            if uid_int <= last_uid:
                continue
            new_max_uid = max(new_max_uid, uid_int)

            _, msg_data = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = str(msg.get("Subject", "")).lower()
            sender = str(msg.get("From", "")).lower()

            for trigger in SUBJECT_TRIGGERS:
                if trigger in subject or trigger in sender:
                    alerts.append(f"{msg.get('Subject', 'no subject')} from {msg.get('From', '?')}")
                    found += 1
                    break

        state["last_uid"] = new_max_uid
        state["scanned_at"] = datetime.now().isoformat()
        save_state(state)
        mail.logout()
        return alerts, found

    except Exception as e:
        log(f"IMAP error: {e}")
        return [], 0
    finally:
        socket.setdefaulttimeout(old_timeout)


def run():
    log("gmail_scanner starting")
    env = load_env()
    user = env.get("GMAIL_ADDRESS", "")
    password = env.get("GMAIL_APP_PASSWORD", "")

    if not user or not password:
        log("ERROR: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set")
        sys.exit(1)

    alerts, found = scan_gmail(user, password)
    log(f"scanned — {found} triggering emails found")

    if alerts:
        try:
            from core.notifier import notify
            msg = "\n".join(f"• {a}" for a in alerts[:5])
            notify("Gmail Alert", msg, urgent=True)
        except Exception as e:
            log(f"notify failed: {e}")

    try:
        from core.event_ledger import log_event
        log_event("system", "gmail_scanner", f"{found} alerts found", score=1.0)
    except Exception:
        pass

    log("gmail_scanner done")


if __name__ == "__main__":
    run()
