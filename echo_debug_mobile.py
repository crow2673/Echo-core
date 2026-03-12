#!/usr/bin/env python3
import subprocess
import re

def listen():
    print("--- Echo Mobile Debug: Notification Content Capture ---")
    # Monitor the notification interface
    cmd = ["dbus-monitor", "interface='org.freedesktop.Notifications',member='Notify'"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    buffer = []
    print("[*] Waiting for phone notification... (Send yourself a text)")

    for line in process.stdout:
        if "string" in line:
            # Extract content between quotes
            match = re.search(r'"([^"]*)"', line)
            if match:
                content = match.group(1)
                # Ignore the standard interface names and IDs
                if content not in ["org.freedesktop.Notifications", ""] and not content.startswith(":"):
                    buffer.append(content)
        
        # When we have a Title and a Body (usually strings 2 and 3 in the Notify sequence)
        if len(buffer) >= 2:
            title = buffer[0]
            body = buffer[1]
            print(f"\n[!] NOTIFICATION DETECTED")
            print(f"    From: {title}")
            print(f"    Message: {body}")
            buffer = [] # Reset for next notification

if __name__ == "__main__":
    listen()
