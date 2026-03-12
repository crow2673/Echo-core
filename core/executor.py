import json
import time
import shlex
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Executor uses a JSON LIST (capsules). Do NOT point this at NDJSON logs.
CAPSULES_FILE = BASE_DIR / "echo_capsules.json"

ALLOWED_PREFIXES = [
    "./echo.py",
    "./workflow_intake_auto.py",
    "python3",
    "python",
    "bash open_outlier.sh",
    "python3 outlier_scan_stub.py",
]
ALLOWED_EXACT = {"outlier-app", "hubstaff-app"}

def load_memory():
    if not CAPSULES_FILE.exists() or CAPSULES_FILE.stat().st_size == 0:
        return []
    try:
        data = json.loads(CAPSULES_FILE.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def save_memory(memory):
    CAPSULES_FILE.write_text(json.dumps(memory, indent=2))

def find_capsule(memory, capsule_id: str):
    for cap in memory:
        if cap.get("capsule_id") == capsule_id:
            return cap
    return None

def allowed_command(argv):
    if not argv:
        return False
    if argv[0] in ALLOWED_EXACT:
        return True
    s = " ".join(argv)
    return any(s.startswith(p) for p in ALLOWED_PREFIXES)

def run_entry_point(ep: str, timeout: int = 600):
    argv = shlex.split(ep)
    if not allowed_command(argv):
        raise RuntimeError(f"Blocked by allowlist: {argv}")
    proc = subprocess.run(
        argv,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    return {
        "argv": argv,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }

def execute_capsule(capsule_id: str, timeout_per_step: int = 600):
    memory = load_memory()
    cap = find_capsule(memory, capsule_id)
    if not cap:
        raise RuntimeError(f"Capsule not found: {capsule_id}")

    cap.setdefault("status", "pending")
    cap.setdefault("attempts", 0)
    cap.setdefault("runs", [])

    if cap.get("approval_required") and not cap.get("approved"):
        cap["status"] = "blocked"
        cap["last_error"] = "Approval required (set approved=true to run)."
        save_memory(memory)
        return {"capsule_id": capsule_id, "status": cap["status"], "last_error": cap.get("last_error")}

    if cap["status"] in ("done", "completed", "success", "succeeded"):
        return {"message": "Already done", "capsule_id": capsule_id}

    cap["status"] = "running"
    cap["attempts"] += 1
    cap["last_started_ts"] = int(time.time())
    save_memory(memory)

    eps = cap.get("entry_points") or []
    results = []
    try:
        for ep in eps:
            r = run_entry_point(ep, timeout=timeout_per_step)
            results.append(r)
            if r["returncode"] != 0:
                raise RuntimeError(f"Entry point failed rc={r['returncode']}: {r['argv']}")

        cap["status"] = "done"
        cap["timestamp"] = int(time.time())
        try:
            prior = int(cap.get("confidence") or 0)
        except (ValueError, TypeError):
            prior = 0
        cap["confidence"] = max(prior, 90)
        cap["verified"] = bool(cap.get("verified")) or True
        cap["last_error"] = None

    except Exception as e:
        cap["status"] = "failed"
        cap["last_error"] = str(e)

    finally:
        cap["runs"].append({"ts": int(time.time()), "results": results})
        save_memory(memory)

    return {"capsule_id": capsule_id, "status": cap["status"], "last_error": cap.get("last_error")}
