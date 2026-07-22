#!/usr/bin/env python3
"""
core/self_build.py — Echo's self-build pipeline.

Echo generates Python scripts from natural language descriptions.
Flow:
  1. Receive description via /build command from Telegram
  2. Call qwen2.5:32b to generate the code
  3. Syntax check with py_compile
  4. Write to builds/pending/<name>.py
  5. Run sandboxed (subprocess, 10s timeout) to catch crashes
  6. Send code preview to Andrew via Telegram
  7. /approve <name> → moves to tools/, deploys
  8. /reject <name>  → deletes, logs reason
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PENDING_DIR = BASE / "builds" / "pending"
DEPLOYED_DIR = BASE / "builds" / "deployed"
BUILD_LOG = BASE / "logs" / "self_build.log"
BUILD_REGISTRY = BASE / "builds" / "registry.json"

PENDING_DIR.mkdir(parents=True, exist_ok=True)
DEPLOYED_DIR.mkdir(parents=True, exist_ok=True)
BUILD_LOG.parent.mkdir(exist_ok=True)

logging.basicConfig(
    filename=BUILD_LOG,
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

sys.path.insert(0, str(BASE))
from core.providers.router import call_ollama


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


# ── Registry ──────────────────────────────────────────────────────────────────
def load_registry():
    if BUILD_REGISTRY.exists():
        try:
            return json.loads(BUILD_REGISTRY.read_text())
        except Exception:
            pass
    return {}


def save_registry(reg):
    tmp = BUILD_REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2))
    tmp.rename(BUILD_REGISTRY)


# ── Code generation ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Echo's internal code generator. You write clean Python 3 scripts for an autonomous AI agent running on Ubuntu Linux.

Build rules you MUST follow:
- Every script starts with #!/usr/bin/env python3 and a one-line docstring
- All file writes use atomic .tmp rename pattern: tmp = path.with_suffix('.tmp'); tmp.write_text(...); tmp.rename(path)
- Every external call (API, subprocess, file I/O) is wrapped in try/except
- Logging goes to logs/<name>.log using the logging module with format "%(asctime)s %(message)s"
- BASE = Path(__file__).resolve().parents[1]  # always use this for all paths
- if __name__ == "__main__": block at the bottom
- Scripts are run by systemd as oneshot — never use while True or time.sleep() loops
- No hardcoded secrets

NOTIFIER (always use this exact pattern — no other way):
    import sys
    sys.path.insert(0, str(BASE))
    from core.notifier import notify
    notify("Title", "message body", urgent=True)   # urgent=True for alerts, False for info
    # notify() signature: notify(title, message, urgent=False, phone=False)
    # NEVER call notifier.py as a subprocess. NEVER use send_notification. ALWAYS import notify.

ENV/SECRETS (always use this exact pattern):
    env_file = Path.home() / ".config/echo/golem.env"
    ENV = {}
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            ENV[k] = v
    # NEVER use dotenv, load_dotenv, or dotenv_values. NEVER use BASE / '.env' or BASE / '.golem.env'

SYSTEM METRICS (use psutil, not subprocess):
    import psutil
    psutil.cpu_percent(interval=2)       # CPU %
    psutil.virtual_memory().percent      # RAM %
    psutil.disk_usage(str(Path.home()))    # disk stats

Output ONLY the Python code. No explanation, no markdown, no code fences. Raw Python only."""


def _slugify(description: str) -> str:
    slug = description.lower().strip()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug)
    return slug[:40]


def generate(description: str) -> dict:
    """Generate a script from a natural language description. Returns build info dict."""
    name = _slugify(description)
    log(f"[self_build] generating: {name}")

    prompt = f"""Write a Python script that does the following:

{description}

The script will run as part of Echo's autonomous agent system on Ubuntu Linux.
It should fit the Echo architecture: read from memory/, write logs to logs/, notify via core/notifier.py if needed."""

    try:
        code = call_ollama(
            prompt=prompt,
            model="qwen2.5:32b",
            timeout=600.0,
            system_prompt=SYSTEM_PROMPT,
        )
    except Exception as e:
        log(f"[self_build] LLM error: {e}")
        return {"ok": False, "error": str(e)}

    # Strip markdown fences if model added them
    code = re.sub(r"^```python\s*", "", code, flags=re.MULTILINE)
    code = re.sub(r"^```\s*$", "", code, flags=re.MULTILINE)
    code = code.strip()

    if not code.startswith("#"):
        code = f"#!/usr/bin/env python3\n{code}"

    # Use the shared safety gate and never deploy as a side effect of generation.
    from core.code_sandbox import run_sandbox
    sandbox_result = run_sandbox(
        code,
        f"{name}.py",
        target_path=f"tools/{name}.py",
        auto_deploy=False,
    )
    syntax_ok = sandbox_result["stage"] != "syntax"
    syntax_error = sandbox_result["reason"] if not syntax_ok else None
    sandbox_ok = sandbox_result["passed"]
    sandbox_output = sandbox_result["reason"]

    # Write to pending
    out_path = PENDING_DIR / f"{name}.py"
    out_path.write_text(code)

    build = {
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
        "syntax_ok": syntax_ok,
        "syntax_error": syntax_error,
        "sandbox_ok": sandbox_ok,
        "sandbox_output": sandbox_output,
        "path": str(out_path),
        "deployed_path": None,
    }

    reg = load_registry()
    reg[name] = build
    save_registry(reg)

    log(f"[self_build] generated {name} — syntax={'ok' if syntax_ok else 'FAIL'}")
    return build


# ── Approval ──────────────────────────────────────────────────────────────────
def approve(name: str, target_dir: str = "tools") -> dict:
    """Move a pending build to tools/ or core/ and mark deployed."""
    reg = load_registry()
    build = reg.get(name)
    if not build:
        return {"ok": False, "error": f"No build named '{name}'"}

    src = PENDING_DIR / f"{name}.py"
    if not src.exists():
        return {"ok": False, "error": f"Pending file not found: {src}"}

    # Archive to deployed/
    archive = DEPLOYED_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    dst = BASE / target_dir / f"{name}.py"

    import shutil
    shutil.copy2(src, archive)
    shutil.move(str(src), str(dst))
    dst.chmod(0o755)

    build["status"] = "deployed"
    build["deployed_path"] = str(dst)
    build["deployed_at"] = datetime.now().isoformat()
    try:
        from core.regret_index import log_action
        build["regret_entry_id"] = log_action(
            action_id=f"generated_tool:{name}",
            category="generated_tool_deploy",
            description=build.get("description", name),
            context="explicit approval or unattended deployment opt-in",
        )
    except Exception as e:
        log(f"[self_build] regret logging failed: {e}")
    reg[name] = build
    save_registry(reg)

    log(f"[self_build] approved and deployed: {dst}")
    return {"ok": True, "path": str(dst), "name": name}


def reject(name: str, reason: str = "") -> dict:
    """
    Reject a pending build, or undo an auto-deployed build by removing it from tools/.
    Works on pending AND deployed builds so /reject can undo an auto-deploy.
    """
    reg = load_registry()
    build = reg.get(name)
    if not build:
        return {"ok": False, "error": f"No build named '{name}'"}

    # Remove pending file if it still exists
    src = PENDING_DIR / f"{name}.py"
    if src.exists():
        src.unlink()

    # If already auto-deployed to tools/, remove it there too
    deployed_path = build.get("deployed_path")
    if deployed_path:
        dp = Path(deployed_path)
        if dp.exists() and str(dp).startswith(str(BASE / "tools")):
            dp.unlink()
            log(f"[self_build] removed auto-deployed file: {dp}")

    build["status"] = "rejected"
    build["rejected_at"] = datetime.now().isoformat()
    build["reject_reason"] = reason
    if build.get("regret_entry_id"):
        try:
            from core.regret_index import update_outcome
            update_outcome(build["regret_entry_id"], -1.0, f"rejected: {reason}")
        except Exception as e:
            log(f"[self_build] regret outcome update failed: {e}")
    reg[name] = build
    save_registry(reg)

    log(f"[self_build] rejected: {name} — {reason}")
    return {"ok": True, "name": name}


def list_pending() -> list:
    reg = load_registry()
    return [b for b in reg.values() if b.get("status") == "pending"]


def get_build(name: str) -> dict:
    return load_registry().get(name, {})


def read_pending_code(name: str) -> str:
    path = PENDING_DIR / f"{name}.py"
    if path.exists():
        return path.read_text()
    return ""


def _infer_interval(description: str) -> str | None:
    """
    Infer a systemd OnUnitActiveSec interval from the build description.
    Returns None if the script appears to be one-shot / on-demand (no timer needed).
    """
    desc = description.lower()
    if any(s in desc for s in ["once", "one-time", "one time", "single run", "on demand", "manual"]):
        return None
    if any(s in desc for s in ["every 15 min", "15min", "15 min"]):
        return "15min"
    if any(s in desc for s in ["every 30 min", "30min", "30 min", "every half hour", "half hour"]):
        return "30min"
    if any(s in desc for s in ["every 2 hour", "every two hour", "2h", "2 hour"]):
        return "2h"
    if any(s in desc for s in ["every 6 hour", "6h", "6 hour", "six hour"]):
        return "6h"
    if any(s in desc for s in ["hourly", "every hour", "each hour", "1h", "per hour"]):
        return "1h"
    if any(s in desc for s in ["daily", "every day", "each day", "24h", "per day", "once a day"]):
        return "24h"
    if any(s in desc for s in ["weekly", "every week", "per week", "once a week"]):
        return "168h"
    # Periodic signal words without explicit interval — default to 1h
    if any(s in desc for s in ["monitor", "alert", "watch", "scan", "check", "report",
                                "tracker", "digest", "summary", "backup"]):
        return "1h"
    return None


def deploy_timer(name: str, path: str, description: str) -> dict:
    """
    Create a systemd service+timer for a deployed script and register in registry.json.

    Called automatically after auto/notify-tier builds are approved. Closes the loop:
    file exists in tools/ → actually runs on a schedule.

    Returns {"ok": True, "timer": "echo-{name}.timer"} or {"ok": False, ...}
    """
    interval = _infer_interval(description)
    if not interval:
        log(f"[deploy_timer] {name}: no interval inferred — skipping timer (one-shot script)")
        return {"ok": False, "skipped": True, "reason": "not a periodic script"}

    service_name = f"echo-{name[:40]}"
    systemd_dir = Path.home() / ".config/systemd/user"
    systemd_dir.mkdir(parents=True, exist_ok=True)

    service_file = systemd_dir / f"{service_name}.service"
    timer_file = systemd_dir / f"{service_name}.timer"

    service_content = (
        "[Unit]\n"
        f"Description=Echo auto-built: {description[:60]}\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "WorkingDirectory=%h/Echo\n"
        f"ExecStart=/usr/bin/python3 {path}\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
    )

    timer_content = (
        "[Unit]\n"
        f"Description=Echo auto-built timer: {description[:60]}\n"
        f"Requires={service_name}.service\n\n"
        "[Timer]\n"
        "OnBootSec=5min\n"
        f"OnUnitActiveSec={interval}\n"
        f"Unit={service_name}.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )

    try:
        service_file.write_text(service_content)
        timer_file.write_text(timer_content)

        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, text=True, timeout=15, check=False
        )
        enable_result = subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{service_name}.timer"],
            capture_output=True, text=True, timeout=15, check=False
        )

        enabled = enable_result.returncode == 0

        # Register in main registry.json
        main_reg = BASE / "registry.json"
        try:
            reg_data = json.loads(main_reg.read_text()) if main_reg.exists() else {"services": {}}
            reg_data["services"][f"{service_name}.timer"] = "active" if enabled else "created"
            reg_data["updated_at"] = datetime.now().isoformat()
            tmp = main_reg.with_suffix(".tmp")
            tmp.write_text(json.dumps(reg_data, indent=2))
            tmp.rename(main_reg)
        except Exception as reg_e:
            log(f"[deploy_timer] registry update failed: {reg_e}")

        status = "active" if enabled else "created (not started)"
        log(f"[deploy_timer] {service_name}.timer {status} — interval={interval}")
        return {"ok": True, "timer": f"{service_name}.timer", "interval": interval, "enabled": enabled}

    except Exception as e:
        log(f"[deploy_timer] error for {name}: {e}")
        return {"ok": False, "error": str(e)}


def check_auto_deploy():
    """
    Deploy any pending 'notify' tier builds whose auto_deploy_after deadline has passed
    and have not been rejected. Called by echo-auto-build-deploy.timer every 15 min.
    """
    if os.environ.get("ECHO_ALLOW_UNATTENDED_DEPLOY") != "1":
        log("[auto-deploy] blocked — ECHO_ALLOW_UNATTENDED_DEPLOY is not enabled")
        return 0

    reg = load_registry()
    now = datetime.now()
    deployed_count = 0

    for name, build in reg.items():
        if build.get("status") != "pending":
            continue
        deadline_str = build.get("auto_deploy_after")
        if not deadline_str:
            continue
        try:
            deadline = datetime.fromisoformat(deadline_str)
        except Exception:
            continue
        if now < deadline:
            continue

        log(f"[auto-deploy] deadline passed for '{name}' — deploying")
        result = approve(name, target_dir="tools")
        if result.get("ok"):
            deployed_count += 1
            deployed_path = result["path"]
            log(f"[auto-deploy] deployed: {deployed_path}")
            # Wire systemd timer so the script actually runs on a schedule
            timer_result = deploy_timer(name, deployed_path, build.get("description", name))
            timer_line = (
                f"Timer: {timer_result['timer']} ({timer_result['interval']})"
                if timer_result.get("ok")
                else "No timer (one-shot script)"
            )
            try:
                from core.notifier import notify
                notify(
                    "Echo auto-deployed build",
                    f"'{name}' deployed to {deployed_path}\n{timer_line}\nTo undo: /reject {name}",
                    urgent=False,
                )
            except Exception:
                pass
        else:
            log(f"[auto-deploy] deploy failed for '{name}': {result.get('error','')}")

    log(f"[auto-deploy] done — {deployed_count} builds deployed")
    return deployed_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["generate", "approve", "reject", "list", "auto-deploy"])
    parser.add_argument("--desc", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.action == "generate":
        result = generate(args.desc)
        print(json.dumps(result, indent=2))
    elif args.action == "approve":
        print(json.dumps(approve(args.name), indent=2))
    elif args.action == "reject":
        print(json.dumps(reject(args.name, args.reason), indent=2))
    elif args.action == "list":
        print(json.dumps(list_pending(), indent=2))
    elif args.action == "auto-deploy":
        check_auto_deploy()
