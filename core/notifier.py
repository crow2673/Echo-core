#!/usr/bin/env python3
import subprocess
import urllib.request
import json
from datetime import datetime

NTFY_TOPIC = "echo-andrew"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

def notify_desktop(title, message, urgency="normal"):
    try:
        subprocess.run(["notify-send", "-u", urgency, f"Echo: {title}", message], capture_output=True)
    except Exception as e:
        print(f"[notifier] desktop error: {e}")

def notify_phone(title, message, priority="default", tags="robot"):
    try:
        data = json.dumps({"topic": NTFY_TOPIC, "title": f"Echo: {title}", "message": message, "priority": priority, "tags": [tags]}).encode()
        req = urllib.request.Request(NTFY_URL, data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[notifier] phone error: {e}")

def notify(title, message, urgent=False, phone=True):
    urgency = "critical" if urgent else "normal"
    priority = "high" if urgent else "default"
    tags = "warning" if urgent else "robot"
    notify_desktop(title, message, urgency)
    if phone:
        notify_phone(title, message, priority, tags)
    print(f"[{datetime.now().strftime('%H:%M')}] notified: {title} — {message[:80]}")

if __name__ == "__main__":
    notify("Test", "Echo outbound communication is working.")
    print("Test sent — check your phone and desktop.")
