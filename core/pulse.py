from datetime import datetime, timezone
from pathlib import Path
import json

p = Path("memory/experience_log.jsonl")
p.parent.mkdir(parents=True, exist_ok=True)

event = {
  "ts": datetime.now(timezone.utc).isoformat(),
  "type": "echo_pulse",
  "source": "echo-pulse.service",
  "note": "daily heartbeat"
}

with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event) + "\n")

print("pulse_ok", event["ts"])
