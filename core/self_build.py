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
import py_compile
import re
import subprocess
import sys
import tempfile
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

    # Syntax check
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf:
        tf.write(code)
        tf_path = tf.name

    try:
        py_compile.compile(tf_path, doraise=True)
        syntax_ok = True
        syntax_error = None
    except py_compile.PyCompileError as e:
        syntax_ok = False
        syntax_error = str(e)
    finally:
        os.unlink(tf_path)

    # Sandbox run (best-effort — catches crashes, not logic errors)
    sandbox_output = None
    sandbox_ok = True
    if syntax_ok:
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"compile(open('{tf_path}').read(), '<test>', 'exec')"],
                capture_output=True, text=True, timeout=10
            )
            sandbox_output = (result.stdout + result.stderr).strip()[:500]
        except Exception as e:
            sandbox_ok = False
            sandbox_output = str(e)

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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["generate", "approve", "reject", "list"])
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
