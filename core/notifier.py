#!/usr/bin/env python3
import os
import subprocess
import urllib.request
import json
from pathlib import Path
from datetime import datetime, timedelta

NTFY_TOPIC = "echo-andrew"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

TELEGRAM_CHAT_ID_FILE = Path.home() / ".config/echo/telegram_chat_id"
MUTE_FILE = Path.home() / ".config/echo/notifications_muted"
BASE = Path(__file__).resolve().parents[1]
NOTIFY_STATE_FILE = BASE / "memory" / "notification_state.json"

TITLE_COOLDOWNS = {
    "Echo: log anomaly": timedelta(hours=6),
    "System Log Error": timedelta(hours=6),
    "System Log Errors": timedelta(hours=6),
    "Echo Log Alerts": timedelta(hours=6),
    "Investment Growth Error": timedelta(hours=24),
}


def _is_muted() -> bool:
    """True while a mute is active. The mute file holds an ISO 'until' timestamp
    (auto-expires and self-deletes), or is empty for an indefinite mute."""
    if not MUTE_FILE.exists():
        return False
    raw = MUTE_FILE.read_text().strip()
    if not raw:
        return True  # indefinite mute
    try:
        if datetime.now() < datetime.fromisoformat(raw):
            return True
        MUTE_FILE.unlink()  # expired — restore notifications
        return False
    except ValueError:
        return True  # unparseable contents -> stay safely muted


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


def _telegram_allowed(title: str, urgent: bool) -> bool:
    """Rate-limit noisy machine alerts without muting real urgent notices globally."""
    cooldown = TITLE_COOLDOWNS.get(title)
    if cooldown is None:
        return True

    now = datetime.now()
    try:
        state = json.loads(NOTIFY_STATE_FILE.read_text()) if NOTIFY_STATE_FILE.exists() else {}
    except Exception:
        state = {}

    last_raw = state.get("telegram_titles", {}).get(title)
    if last_raw:
        try:
            if now - datetime.fromisoformat(last_raw) < cooldown:
                print(f"[notifier] telegram throttled: {title}")
                return False
        except ValueError:
            pass

    state.setdefault("telegram_titles", {})[title] = now.isoformat(timespec="seconds")
    NOTIFY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTIFY_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(NOTIFY_STATE_FILE)
    return True


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


def _is_game_running() -> bool:
    """Check if a fullscreen game is running that desktop popups would disrupt."""
    games = ["aces", "warthunder", "steam", "wine"]
    try:
        result = subprocess.run(["pgrep", "-f", "|".join(games)], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def notify_desktop(title, message, urgency="normal"):
    if _is_muted():
        return
    if _is_game_running():
        print(f"[notifier] desktop suppressed (game running): {title}")
        return
    try:
        # Auto-expire after 6s, never steal focus
        cmd = ["notify-send", "-u", urgency, "-t", "6000"]
        # low-urgency (e.g. bus watchers): keep it quiet + non-interrupting —
        # suppress the chime and mark transient so it slips into the notification
        # center without a persistent banner over the foreground app.
        if urgency == "low":
            cmd += ["-h", "byte:suppress-sound:1", "-h", "byte:transient:1"]
        cmd += [f"Echo: {title}", message]
        subprocess.run(cmd, capture_output=True)
    except Exception as e:
        print(f"[notifier] desktop error: {e}")


def notify_phone(title, message, priority="default", tags="robot"):
    if _is_muted():
        return
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
    if _is_muted():
        return
    if not _telegram_allowed(title, urgent):
        return
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


def notify(title, message, urgent=False, phone=True, desktop=False):
    if _is_muted():
        print(f"[notifier] muted — suppressed: {title}")
        return
    urgency = "critical" if urgent else "normal"
    # Desktop only for urgent alerts, and only when no game is running
    if desktop or urgent:
        notify_desktop(title, message, urgency)
    if phone:
        notify_telegram(title, message, urgent=urgent)
    print(f"[{datetime.now().strftime('%H:%M')}] notified: {title} — {message[:80]}")


if __name__ == "__main__":
    notify("Test", "Echo outbound communication is working.")
    print("Test sent — check your phone, desktop, and Telegram.")
