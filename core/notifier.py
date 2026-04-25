#!/usr/bin/env python3
import os
import subprocess
import urllib.request
import json
from pathlib import Path
from datetime import datetime

NTFY_TOPIC = "echo-andrew"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

TELEGRAM_CHAT_ID_FILE = Path.home() / ".config/echo/telegram_chat_id"


def _get_telegram_config() -> tuple[str, str]:
    """Return (bot_token, chat_id) or ('', '') if not configured."""
    env_file = Path.home() / ".config/echo/golem.env"
    token = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # chat_id stored separately (auto-discovered on first message)
    chat_id = ""
    if TELEGRAM_CHAT_ID_FILE.exists():
        chat_id = TELEGRAM_CHAT_ID_FILE.read_text().strip()
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    return token, chat_id


def _discover_telegram_chat_id(token: str) -> str:
    """Try to auto-discover chat_id from the most recent bot update."""
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getUpdates?limit=10&allowed_updates=[\"message\"]",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("result", [])
        for r in reversed(results):
            chat_id = str(r.get("message", {}).get("chat", {}).get("id", ""))
            if chat_id:
                TELEGRAM_CHAT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
                TELEGRAM_CHAT_ID_FILE.write_text(chat_id)
                print(f"[notifier] Telegram chat_id discovered and saved: {chat_id}")
                return chat_id
    except Exception:
        pass
    return ""


def notify_desktop(title, message, urgency="normal"):
    try:
        subprocess.run(["notify-send", "-u", urgency, f"Echo: {title}", message], capture_output=True)
    except Exception as e:
        print(f"[notifier] desktop error: {e}")


def notify_phone(title, message, priority="default", tags="robot"):
    try:
        data = json.dumps({
            "topic": NTFY_TOPIC, "title": f"Echo: {title}",
            "message": message, "priority": priority, "tags": [tags]
        }).encode()
        req = urllib.request.Request(
            NTFY_URL, data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[notifier] phone error: {e}")


def notify_telegram(title, message, urgent=False):
    """Send message via Telegram bot. Auto-discovers chat_id on first use."""
    token, chat_id = _get_telegram_config()
    if not token:
        return  # Not configured

    if not chat_id:
        chat_id = _discover_telegram_chat_id(token)
    if not chat_id:
        return  # Can't reach — Andrew hasn't messaged the bot yet

    emoji = "🚨" if urgent else "🤖"
    # Use plain text — Markdown mode breaks on em dashes and other unicode
    text = f"{emoji} Echo: {title}\n{message}"
    try:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[notifier] telegram error: {e}")


def notify(title, message, urgent=False, phone=True):
    urgency = "critical" if urgent else "normal"
    priority = "high" if urgent else "default"
    tags = "warning" if urgent else "robot"
    notify_desktop(title, message, urgency)
    if phone:
        notify_telegram(title, message, urgent=urgent)
    print(f"[{datetime.now().strftime('%H:%M')}] notified: {title} — {message[:80]}")


if __name__ == "__main__":
    notify("Test", "Echo outbound communication is working.")
    print("Test sent — check your phone, desktop, and Telegram.")
