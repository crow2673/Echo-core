import subprocess
import json
import time
from pathlib import Path

OUT_JSONL = Path.home() / "Echo" / "memory" / "golem_pure.jsonl"
OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

YAGNA = str(Path.home() / ".local" / "bin" / "yagna")

def run_json(cmd, timeout=30):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)} :: {r.stderr.strip()[:300]}")
    try:
        return json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"expected JSON but got: {r.stdout[:300]}")

def main():
    ts = time.time()
    status = run_json([YAGNA, "payment", "status", "--network", "polygon", "--json"])

    # Normalize likely fields (defensive)
    amount = None
    token = None
    network = status.get("network")
    driver = status.get("driver")

    # Some versions give amount/token at top-level
    if isinstance(status.get("amount"), (str, int, float)):
        amount = float(status["amount"])
    if isinstance(status.get("token"), str):
        token = status["token"]

    # If it’s nested differently, keep raw but still log
    log = {
        "ts": ts,
        "type": "golem_payment_status",
        "network": network,
        "driver": driver,
        "amount": amount,
        "token": token,
        "raw": status,   # keep full JSON so you never lose truth
    }

    with OUT_JSONL.open("a") as f:
        f.write(json.dumps(log) + "\n")

    # Simple human output (useful for cron/systemd logs)
    print(f"[golem] network={network} driver={driver} amount={amount} token={token}")

if __name__ == "__main__":
    main()
