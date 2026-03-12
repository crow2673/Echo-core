#!/usr/bin/env python3
"""
Safe bridge to chat with Echo without breaking autonomy.
Uses echo_intake.py to send commands and get acknowledgments.
"""

import subprocess

PROMPT = "Andrew > "
BOT_PREFIX = "Echo > "

def send_to_echo(msg: str):
    cmd = [
        "python3",
        "echo_message_intake.py",
        "--from",
        "andrew",
        "--text",
        msg,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"error sending message: {e}\n{e.stderr}"
def main():
    print(f"{BOT_PREFIX}chat bridge online. Type 'exit' to quit.")
    while True:
        try:
            msg = input(PROMPT).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{BOT_PREFIX}goodbye")
            break

        if not msg:
            continue
        if msg.lower() in {"exit", "quit"}:
            print(f"{BOT_PREFIX}goodbye")
            break

        response = send_to_echo(msg)
        print(f"{BOT_PREFIX}{response}")

if __name__ == "__main__":
    main()
