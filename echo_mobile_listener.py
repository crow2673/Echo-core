#!/usr/bin/env python3
import subprocess
import re

def send_to_echo(text: str):
    # Queue as a message so the core daemon can process it
    cmd = [
        "python3",
        "echo_message_intake.py",
        "--from",
        "mobile",
        "--text",
        text,
    ]
    subprocess.run(cmd, check=False)

def listen():
    print("--- Echo Mobile Bridge: Inbox Mode ---")
    cmd = ["dbus-monitor", "interface='org.freedesktop.Notifications',member='Notify'"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    for line in process.stdout:
        if "string" not in line:
            continue

        match = re.search(r'"([^"]*)"', line)
        if not match:
            continue

        content = match.group(1)

        # Keep your existing trigger behavior:
        if "Power" in content and any(ch.isdigit() for ch in content):
            send_to_echo(f"[MOBILE_NOTIF] {content}")

if __name__ == "__main__":
    listen()
