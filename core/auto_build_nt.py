import json
import subprocess
import requests
import time
from threading import Thread
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
INTAKE = BASE / "echo_message_intake.py"

def listen_for_ntfy_messages(topic, auth_token):

    def handle_message(message):
        try:
            result = subprocess.run(
                ["python3", str(INTAKE), "--text", message],
                capture_output=True, text=True, timeout=120
            )
            reply = result.stdout.strip()
            if reply:
                send_ntfy_reply(reply)
        except Exception as e:
            print(f"Error processing message: {e}")

    def send_ntfy_reply(message):
        try:
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            response = requests.post(
                f"https://ntfy.sh/{topic}",
                data=message.encode("utf-8"),
                headers=headers
            )
            if not response.ok:
                print(f"Failed to post reply: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error sending ntfy reply: {e}")

    backoff = 5
    while True:
        try:
            # Small delay on first connect to survive boot clock skew
            time.sleep(2)
            since = int(time.time())
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            response = requests.get(
                f"https://ntfy.sh/{topic}/json?since={since}",
                stream=True,
                headers=headers,
                timeout=90
            )
            if response.status_code == 200:
                backoff = 5  # reset on success
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if data.get("event") == "message":
                                handle_message(data.get("message", ""))
                        except Exception as e:
                            print(f"Parse error: {e}")
            else:
                print(f"ntfy subscribe failed: {response.status_code}, retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
        except Exception as e:
            print(f"Connection error: {e}, retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--auth-token", required=False, default="")
    args = parser.parse_args()

    t = Thread(target=listen_for_ntfy_messages, args=(args.topic, args.auth_token))
    t.daemon = True
    t.start()
    t.join()
