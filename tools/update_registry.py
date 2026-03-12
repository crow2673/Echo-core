#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

base = Path("/home/andrew/Echo")
sys.path.insert(0, str(base))

from echo_memory_sqlite import get_memory

units = subprocess.run(
    ["systemctl", "--user", "list-units", "--all", "--no-legend"],
    capture_output=True, text=True
).stdout

r = json.loads((base / "registry.json").read_text())
r["generated_at"] = datetime.now().isoformat()
r["memory"]["total_memories"] = get_memory().count()
r["active_services"] = [l.split()[0] for l in units.splitlines() if "echo-" in l and ".service" in l]
r["active_timers"] = [l.split()[0] for l in units.splitlines() if "echo-" in l and ".timer" in l]
(base / "registry.json").write_text(json.dumps(r, indent=2))
print(f"Registry updated: {len(r['active_services'])} services, {r['memory']['total_memories']} memories")
