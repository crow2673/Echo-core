import json
import subprocess
import requests
import time
import queue
from threading import Thread
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
INTAKE = BASE / "echo_message_intake.py"

message_queue = queue.Queue()

def send_ntfy_reply(message, topic, auth_token):
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=15
        )
        if not response.ok:
            print(f"Failed to post reply: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending ntfy reply: {e}")

def processor_worker(topic, auth_token):
    """Dedicated thread: pulls from queue, calls intake, sends reply. Never blocks listener."""
    while True:
        try:
            message = message_queue.get(timeout=5)
        except queue.Empty:
            continue
        try:
            print(f"Processing: {message[:80]}")
            result = subprocess.run(
                ["python3", str(INTAKE), "--text", message],
                capture_output=True, text=True, timeout=180
            )
            reply = result.stdout.strip()
            if reply:
                send_ntfy_reply(reply, topic, auth_token)
        except Exception as e:
            print(f"Error processing message: {e}")
        finally:
            message_queue.task_done()

def listener_worker(topic, auth_token):
    """Dedicated thread: streams ntfy, drops messages into queue immediately."""
    backoff = 5
    while True:
        try:
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
                backoff = 5
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if data.get("event") == "message":
                                msg = data.get("message", "")
                                if msg:
                                    message_queue.put(msg)
                                    print(f"Queued message ({message_queue.qsize()} in queue)")
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

    # Start processor first so it's ready before messages arrive
    proc = Thread(target=processor_worker, args=(args.topic, args.auth_token), daemon=True)
    proc.start()

    # Listener runs in main thread
    listener_worker(args.topic, args.auth_token)
