#!/usr/bin/env python3
"""
core/app_builder.py — Multi-file app generation for Echo.

Extends self_build to support full applications, not just single scripts:
  - Flask/FastAPI web apps with templates + static assets
  - REST APIs
  - Telegram bots
  - CLI tools with multiple modules
  - Background services
  - Standalone HTML/JS apps

Flow:
  1. LLM designs the file structure given a description
  2. LLM generates each file sequentially (each sees previously generated files as context)
  3. Python files are syntax-checked
  4. All files written to builds/apps/<name>/
  5. Requirements installed if requirements.txt present
  6. Systemd service/timer created and enabled
  7. Andrew notified with URL (if web) or /reject <name> undo option

Tier: all apps go through "notify" — Andrew gets a 2h window to /rejectapp before deploy.
Gate signals (trading logic, core/ files) always require explicit /approveapp.
"""
import json
import logging
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APPS_DIR = BASE / "builds" / "apps"
APP_LOG = BASE / "logs" / "app_builder.log"

APPS_DIR.mkdir(parents=True, exist_ok=True)
APP_LOG.parent.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(APP_LOG),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)

sys.path.insert(0, str(BASE))
from core.providers.router import call_ollama


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


# ── Planner ───────────────────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are Echo's app architect. Given an app description, output a JSON plan for the files needed.

Output ONLY valid JSON. No explanation, no markdown, no code fences.

JSON format:
{
  "app_name": "short_snake_case_name_max_30_chars",
  "app_type": "web|api|bot|cli|service",
  "entry_point": "app.py",
  "port": null,
  "description": "one sentence what this app does",
  "files": [
    {"path": "app.py", "purpose": "one sentence role", "language": "python"},
    {"path": "templates/index.html", "purpose": "...", "language": "html"},
    {"path": "static/style.css", "purpose": "...", "language": "css"},
    {"path": "requirements.txt", "purpose": "pip dependencies", "language": "text"}
  ]
}

Rules:
- app_type "web": Flask app with templates/index.html, templates/base.html, static/style.css, requirements.txt
- app_type "api": FastAPI app with models.py, routes/, requirements.txt
- app_type "bot": Telegram/Discord bot with bot.py, requirements.txt
- app_type "cli": Python CLI with just the Python files needed
- app_type "service": Background worker Python files, no UI
- port: null for cli/service/bot; pick 8080-8099 for web; 8100-8199 for api
- Keep it focused: 3-8 files max. No test files, no __init__.py unless required.
- app_name must be short snake_case, no spaces, max 30 chars
"""


# ── Generator ─────────────────────────────────────────────────────────────────

GENERATOR_SYSTEM = """You are Echo's code generator. Write the content for a single file in a multi-file application.

PATH CONTEXT — apps live at ~/Echo/builds/apps/<name>/:
  APP_DIR = Path(__file__).resolve().parent          # this app's directory
  ECHO_BASE = Path(__file__).resolve().parents[3]    # ~/Echo/ root

Python rules:
- #!/usr/bin/env python3 header + one-line docstring
- Use ECHO_BASE (parents[3]) for Echo memory/log paths, APP_DIR (parent) for app-local paths
- All external calls wrapped in try/except
- Logging: logging.basicConfig(filename=str(ECHO_BASE / "logs/<app_name>.log"), ...)
- Flask: use Flask(__name__) — templates/static folders auto-resolve from app's directory
- FastAPI: include if __name__ == "__main__": import uvicorn; uvicorn.run(app, host="0.0.0.0", port=PORT)
- No hardcoded secrets — read from Path.home() / ".config/echo/golem.env"
- Atomic file writes: tmp = path.with_suffix('.tmp'); tmp.write_text(...); tmp.rename(path)

HTML rules:
- Clean HTML5, mobile-friendly
- Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
- No npm, no build step required
- Dark mode friendly (prefer dark bg, light text)

CSS rules:
- Minimal, mobile-first. Use variables for colors.

requirements.txt rules:
- One package per line, no version pins unless critical
- stdlib modules are NOT listed (json, pathlib, logging, etc.)

Output ONLY the file content. No explanation, no markdown fences."""


def _next_available_port(preferred: int | None, app_type: str) -> int:
    """Find an unused port in the Echo apps range."""
    used = set()
    if APPS_DIR.exists():
        for app_dir in APPS_DIR.iterdir():
            meta = app_dir / "echo_app.json"
            if meta.exists():
                try:
                    p = json.loads(meta.read_text()).get("port")
                    if p:
                        used.add(p)
                except Exception:
                    pass

    base_port = 8100 if app_type == "api" else 8080
    limit = base_port + 100
    if preferred and base_port <= preferred < limit and preferred not in used:
        return preferred
    for port in range(base_port, limit):
        if port not in used:
            return port
    return base_port


def plan_app(description: str) -> dict:
    """Ask LLM to design the app file structure. Returns parsed plan dict."""
    prompt = f"Design the file structure for this application:\n\n{description}"
    raw = call_ollama(
        prompt=prompt,
        model="qwen2.5:7b",
        timeout=60.0,
        system_prompt=PLANNER_SYSTEM,
    )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"^```\s*$", "", raw, flags=re.MULTILINE)
    return json.loads(raw.strip())


def generate_file(file_info: dict, plan: dict, existing_files: dict) -> str:
    """Generate one file's content. Each file sees all previously generated files as context."""
    ctx_parts = [
        f"App name: {plan.get('app_name', '')}",
        f"App type: {plan.get('app_type', '')}",
        f"Description: {plan.get('description', '')}",
        f"Entry point: {plan.get('entry_point', 'app.py')}",
    ]
    if plan.get("port"):
        ctx_parts.append(f"Port: {plan['port']}")

    all_files = [f["path"] for f in plan.get("files", [])]
    ctx_parts.append(f"All files in this app: {', '.join(all_files)}")

    if existing_files:
        ctx_parts.append("\nAlready generated files (use these for imports and cross-references):")
        for path, content in existing_files.items():
            preview = content[:500] + ("..." if len(content) > 500 else "")
            ctx_parts.append(f"\n--- {path} ---\n{preview}")

    context = "\n".join(ctx_parts)
    prompt = (
        f"Application context:\n{context}\n\n"
        f"Generate the content for: {file_info['path']}\n"
        f"Purpose: {file_info['purpose']}"
    )
    return call_ollama(
        prompt=prompt,
        model="qwen2.5:32b",
        timeout=600.0,
        system_prompt=GENERATOR_SYSTEM,
    )


def build_app(description: str) -> dict:
    """
    Full multi-file app build pipeline.
    Returns {"ok": True, "app_dir": str, "app_name": str, "plan": dict, "meta": dict}
         or {"ok": False, "error": str}
    """
    log(f"[app_builder] planning app: {description[:80]}")

    try:
        plan = plan_app(description)
    except Exception as e:
        log(f"[app_builder] planning failed: {e}")
        return {"ok": False, "error": f"planning failed: {e}"}

    app_name = re.sub(r"[^a-z0-9_]", "_", plan.get("app_name", "app").lower())[:30]
    app_name = app_name.strip("_") or "app"
    files_to_gen = plan.get("files", [])

    if not files_to_gen:
        return {"ok": False, "error": "planner returned no files"}

    app_type = plan.get("app_type", "cli")
    if app_type in ("web", "api"):
        plan["port"] = _next_available_port(plan.get("port"), app_type)

    log(f"[app_builder] {app_name} ({app_type}) — {len(files_to_gen)} files planned")

    app_dir = APPS_DIR / app_name
    app_dir.mkdir(parents=True, exist_ok=True)

    existing_files: dict[str, str] = {}
    syntax_errors: list[dict] = []

    for file_info in files_to_gen:
        file_path = file_info["path"]
        language = file_info.get("language", "text")
        log(f"[app_builder]   generating: {file_path}")

        try:
            content = generate_file(file_info, plan, existing_files)
        except Exception as e:
            log(f"[app_builder]   FAILED {file_path}: {e}")
            content = f"# Generation failed: {e}\n"

        # Strip markdown fences if model added them
        content = re.sub(r"^```\w*\s*\n?", "", content.strip(), flags=re.MULTILINE)
        content = re.sub(r"\n?^```\s*$", "", content, flags=re.MULTILINE)
        content = content.strip()

        # Ensure Python files have shebang
        if (language == "python" or file_path.endswith(".py")) and not content.startswith("#"):
            content = "#!/usr/bin/env python3\n" + content

        # Syntax check Python files
        if language == "python" or file_path.endswith(".py"):
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf:
                tf.write(content)
                tf_path = tf.name
            try:
                py_compile.compile(tf_path, doraise=True)
            except py_compile.PyCompileError as e:
                syntax_errors.append({"file": file_path, "error": str(e)})
                log(f"[app_builder]   syntax error in {file_path}: {e}")
            finally:
                os.unlink(tf_path)

        out_path = app_dir / file_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content)
        existing_files[file_path] = content

    meta = {
        "app_name": app_name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "status": "built",
        "app_type": app_type,
        "entry_point": plan.get("entry_point", "app.py"),
        "port": plan.get("port"),
        "files": [f["path"] for f in files_to_gen],
        "syntax_errors": syntax_errors,
        "auto_deploy_after": (datetime.now() + timedelta(hours=2)).isoformat(),
    }
    (app_dir / "echo_app.json").write_text(json.dumps(meta, indent=2))

    log(f"[app_builder] built {app_name} — {len(existing_files)} files, {len(syntax_errors)} syntax errors")
    return {
        "ok": True,
        "app_dir": str(app_dir),
        "app_name": app_name,
        "plan": plan,
        "meta": meta,
    }


def deploy_app(app_name: str) -> dict:
    """
    Deploy a built app: install deps, create systemd unit, register in registry.json.
    Called after Andrew's 2h window passes without /rejectapp, or on /approveapp.
    """
    app_dir = APPS_DIR / app_name
    meta_file = app_dir / "echo_app.json"
    if not app_dir.exists() or not meta_file.exists():
        return {"ok": False, "error": f"App '{app_name}' not found"}

    meta = json.loads(meta_file.read_text())
    app_type = meta.get("app_type", "cli")
    entry_point = meta.get("entry_point", "app.py")
    port = meta.get("port")
    entry_path = app_dir / entry_point

    if not entry_path.exists():
        return {"ok": False, "error": f"Entry point not found: {entry_path}"}

    # Install requirements if present
    req_file = app_dir / "requirements.txt"
    if req_file.exists():
        # Strip stdlib modules — LLM sometimes includes json, os, sys, etc.
        _STDLIB = {
            "json", "os", "sys", "re", "math", "time", "datetime", "pathlib",
            "logging", "hashlib", "random", "string", "io", "csv", "copy",
            "collections", "itertools", "functools", "typing", "abc", "enum",
            "threading", "subprocess", "shutil", "tempfile", "glob", "struct",
            "base64", "urllib", "http", "socket", "ssl", "email", "html",
            "xml", "sqlite3", "unittest", "traceback", "inspect", "ast",
            "contextlib", "dataclasses", "weakref", "gc", "platform", "signal",
        }
        raw_lines = req_file.read_text().splitlines()
        clean_lines = []
        invalid_lines = []
        seen = set()
        requirement_pattern = re.compile(
            r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?"
            r"(?:\s*(?:==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9*+_.-]+)?$"
        )
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            package = re.split(r"[=<>!~\[]", line, maxsplit=1)[0].strip().lower()
            if package in _STDLIB:
                continue
            if not requirement_pattern.fullmatch(line):
                invalid_lines.append(line)
                continue
            key = line.lower()
            if key not in seen:
                clean_lines.append(line)
                seen.add(key)

        if invalid_lines:
            return _mark_deploy_failed(
                meta_file, meta, f"invalid requirements: {invalid_lines[:3]}"
            )
        if len(clean_lines) > 20:
            return _mark_deploy_failed(
                meta_file, meta, f"too many requirements ({len(clean_lines)}; max 20)"
            )
        if len(clean_lines) < len([l for l in raw_lines if l.strip() and not l.strip().startswith("#")]):
            filtered = [l for l in raw_lines if l.strip() and not l.strip().startswith("#") and l not in clean_lines]
            log(f"[app_builder] stripped stdlib from requirements: {filtered}")
            req_file.write_text("\n".join(clean_lines) + "\n")

        if clean_lines:
            log(f"[app_builder] installing requirements for {app_name}")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_file),
                     "--quiet", "--break-system-packages"],
                    capture_output=True, text=True, timeout=180, check=False,
                )
                if result.returncode != 0:
                    log(f"[app_builder] pip warnings: {result.stderr[:300]}")
                    return _mark_deploy_failed(
                        meta_file, meta, f"pip install failed: {result.stderr[:300]}"
                    )
            except Exception as e:
                log(f"[app_builder] pip install failed: {e}")
                return _mark_deploy_failed(meta_file, meta, f"pip install failed: {e}")

    service_name = f"echo-app-{app_name[:28]}"
    systemd_dir = Path.home() / ".config/systemd/user"
    systemd_dir.mkdir(parents=True, exist_ok=True)

    if app_type in ("web", "api"):
        # Generated API apps commonly use relative imports, so run them as packages.
        (app_dir / "__init__.py").touch(exist_ok=True)
        for py_file in app_dir.rglob("*.py"):
            if py_file.parent != app_dir:
                (py_file.parent / "__init__.py").touch(exist_ok=True)
        module = f"{app_name}.{Path(entry_point).with_suffix('').as_posix().replace('/', '.')}"

        # Persistent service — stays running, restarts on failure
        service_content = (
            "[Unit]\n"
            f"Description=Echo App: {meta.get('description', app_name)[:60]}\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={APPS_DIR}\n"
            f"ExecStart=/usr/bin/python3 -m {module}\n"
            "Restart=on-failure\n"
            "RestartSec=10s\n"
            "StandardOutput=journal\n"
            "StandardError=journal\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        svc_file = systemd_dir / f"{service_name}.service"
        svc_file.write_text(service_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=15)
        enable = subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{service_name}.service"],
            capture_output=True, text=True, timeout=15,
        )
        enabled = enable.returncode == 0
        unit_key = f"{service_name}.service"
        if enabled:
            time.sleep(2)
            active = subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit_key],
                capture_output=True, timeout=10,
            )
            enabled = active.returncode == 0
        if not enabled:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", unit_key],
                capture_output=True, timeout=15,
            )
            return _mark_deploy_failed(
                meta_file, meta, f"service failed startup: {enable.stderr[:300]}"
            )
        log(f"[app_builder] web service {'started' if enabled else 'failed to start'}: {service_name}")

    else:
        # Oneshot + timer for cli/service/bot
        service_content = (
            "[Unit]\n"
            f"Description=Echo App: {meta.get('description', app_name)[:60]}\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            f"WorkingDirectory={app_dir}\n"
            f"ExecStart=/usr/bin/python3 {entry_path}\n"
            "StandardOutput=journal\n"
            "StandardError=journal\n"
        )
        timer_content = (
            "[Unit]\n"
            f"Description=Echo App timer: {app_name}\n"
            f"Requires={service_name}.service\n\n"
            "[Timer]\n"
            "OnBootSec=5min\n"
            "OnUnitActiveSec=1h\n"
            f"Unit={service_name}.service\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )
        (systemd_dir / f"{service_name}.service").write_text(service_content)
        (systemd_dir / f"{service_name}.timer").write_text(timer_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=15)
        enable = subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{service_name}.timer"],
            capture_output=True, text=True, timeout=15,
        )
        enabled = enable.returncode == 0
        unit_key = f"{service_name}.timer"

    # Register in main registry.json
    main_reg = BASE / "registry.json"
    try:
        reg_data = json.loads(main_reg.read_text()) if main_reg.exists() else {"services": {}}
        reg_data["services"][unit_key] = "active" if enabled else "created"
        reg_data.setdefault("apps", {})[app_name] = {
            "description": meta.get("description", ""),
            "app_type": app_type,
            "port": port,
            "url": f"http://localhost:{port}" if port else None,
            "deployed_at": datetime.now().isoformat(),
        }
        reg_data["updated_at"] = datetime.now().isoformat()
        tmp = main_reg.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg_data, indent=2))
        tmp.rename(main_reg)
    except Exception as e:
        log(f"[app_builder] registry update failed: {e}")

    meta["status"] = "deployed"
    meta["deployed_at"] = datetime.now().isoformat()
    meta["service_name"] = service_name
    try:
        from core.regret_index import log_action
        meta["regret_entry_id"] = log_action(
            action_id=f"generated_app:{app_name}",
            category="generated_app_deploy",
            description=meta.get("description", app_name),
            context="explicit approval or unattended deployment opt-in",
        )
    except Exception as e:
        log(f"[app_builder] regret logging failed: {e}")
    meta.pop("deploy_error", None)
    meta.pop("deploy_failed_at", None)
    (app_dir / "echo_app.json").write_text(json.dumps(meta, indent=2))

    url = f"http://localhost:{port}" if port else None
    log(f"[app_builder] deployed {app_name}" + (f" at {url}" if url else ""))
    return {"ok": True, "app_name": app_name, "service": service_name, "url": url, "enabled": enabled}


def _mark_deploy_failed(meta_file: Path, meta: dict, error: str) -> dict:
    """Record a terminal deploy failure so auto-deploy does not retry forever."""
    meta["status"] = "deploy_failed"
    meta["deploy_failed_at"] = datetime.now().isoformat()
    meta["deploy_error"] = error
    meta_file.write_text(json.dumps(meta, indent=2))
    log(f"[app_builder] deployment blocked for {meta.get('app_name', 'app')}: {error}")
    return {"ok": False, "error": error}


def reject_app(app_name: str, reason: str = "") -> dict:
    """Mark an app as rejected and stop/remove its systemd unit if deployed."""
    app_dir = APPS_DIR / app_name
    meta_file = app_dir / "echo_app.json"
    if not meta_file.exists():
        return {"ok": False, "error": f"App '{app_name}' not found"}

    meta = json.loads(meta_file.read_text())
    service_name = meta.get("service_name", f"echo-app-{app_name[:28]}")
    app_type = meta.get("app_type", "cli")
    unit = f"{service_name}.service" if app_type in ("web", "api") else f"{service_name}.timer"

    systemd_dir = Path.home() / ".config/systemd/user"
    for suffix in (".service", ".timer"):
        unit_file = systemd_dir / f"{service_name}{suffix}"
        if unit_file.exists():
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", f"{service_name}{suffix}"],
                capture_output=True, timeout=10,
            )
            unit_file.unlink()

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=15)

    meta["status"] = "rejected"
    meta["rejected_at"] = datetime.now().isoformat()
    meta["reject_reason"] = reason
    if meta.get("regret_entry_id"):
        try:
            from core.regret_index import update_outcome
            update_outcome(meta["regret_entry_id"], -1.0, f"rejected: {reason}")
        except Exception as e:
            log(f"[app_builder] regret outcome update failed: {e}")
    meta_file.write_text(json.dumps(meta, indent=2))

    log(f"[app_builder] rejected app: {app_name} — {reason}")
    return {"ok": True, "app_name": app_name}


def list_apps(status_filter: str | None = None) -> list[dict]:
    """List built apps, optionally filtered by status."""
    apps = []
    if not APPS_DIR.exists():
        return apps
    for app_dir in sorted(APPS_DIR.iterdir()):
        meta_file = app_dir / "echo_app.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                if status_filter is None or meta.get("status") == status_filter:
                    apps.append(meta)
            except Exception:
                pass
    return apps


def check_auto_deploy_apps():
    """
    Deploy any built apps whose auto_deploy_after deadline has passed
    and haven't been rejected. Called by echo-auto-build-deploy.timer.
    """
    if os.environ.get("ECHO_ALLOW_UNATTENDED_DEPLOY") != "1":
        log("[auto-deploy-app] blocked — ECHO_ALLOW_UNATTENDED_DEPLOY is not enabled")
        return 0

    now = datetime.now()
    deployed_count = 0
    for app in list_apps(status_filter="built"):
        deadline_str = app.get("auto_deploy_after")
        if not deadline_str:
            continue
        try:
            if now < datetime.fromisoformat(deadline_str):
                continue
        except Exception:
            continue

        app_name = app["app_name"]
        log(f"[auto-deploy-app] deadline passed for '{app_name}' — deploying")
        result = deploy_app(app_name)
        if result.get("ok"):
            deployed_count += 1
            url_line = f"\nLive at: {result['url']}" if result.get("url") else ""
            try:
                from core.notifier import notify
                notify(
                    "Echo deployed an app",
                    f"'{app_name}' is now live.{url_line}\nTo stop: /rejectapp {app_name}",
                    urgent=False,
                )
            except Exception:
                pass
        else:
            log(f"[auto-deploy-app] failed for '{app_name}': {result.get('error','')}")

    return deployed_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "deploy", "reject", "list", "auto-deploy"])
    parser.add_argument("--desc", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.action == "build":
        print(json.dumps(build_app(args.desc), indent=2, default=str))
    elif args.action == "deploy":
        print(json.dumps(deploy_app(args.name), indent=2))
    elif args.action == "reject":
        print(json.dumps(reject_app(args.name, args.reason), indent=2))
    elif args.action == "list":
        print(json.dumps(list_apps(), indent=2, default=str))
    elif args.action == "auto-deploy":
        check_auto_deploy_apps()
