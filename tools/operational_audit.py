#!/usr/bin/env python3
"""Audit Echo's operational drift after updates, outages, and self-builds.

This is a local, read-mostly check. It does not repair anything; it records the
things that make a persistent agent brittle: failed units, stale state, Python
venv drift, missing imports, generated-app sprawl, and oversized logs/memory.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "memory/operational_audit.json"
LOG = BASE / "logs/operational_audit.log"

CRITICAL_UNITS = {
    "echo-core.service",
    "echo-governor-v2.timer",
    "echo-circuit-breaker.timer",
    "echo-telegram-intake.timer",
    "echo-self-act-worker.timer",
    "echo-conductor-agents-repair.timer",
}

OPTIONAL_FAILED_UNITS = {
    "echo-finetune.service",
}

DEFERRED_DELIVERY_UNITS = {
    "echo-offsite-backup.service",
}

CORE_IMPORTS = {
    "psutil": "core stats",
    "requests": "HTTP clients",
    "pandas": "data/backtests",
    "playwright": "browser automation",
}

APP_IMPORTS = {
    "flask": "Crow Finance and generated Flask apps",
}

ARCHIVAL_MEMORY_DIRS = {
    "archive_consolidated",
    "obsidian_vault",
    "opportunities",
    "finetune_data",
    "exported_models",
    "lora_adapters",
    "ollama",
    "articles",
    "blog",
    "weekly_reports",
    "income_reports",
    "product_pages",
    "newsletter_drafts",
    "outreach_drafts",
}


def run_cmd(args: list[str], timeout: int = 10) -> dict:
    try:
        result = subprocess.run(
            args,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}


def offsite_backup_transport_deferred() -> bool:
    path = BASE / "memory/offsite_backup_status.json"
    try:
        if not path.exists():
            return False
        status = json.loads(path.read_text())
        artifact = status.get("artifact_path")
        return bool(
            status.get("local_backup_created")
            and status.get("encryption_completed")
            and status.get("offsite_delivery_pending")
            and artifact
            and (BASE / artifact).exists()
        )
    except Exception:
        return False


def systemd_snapshot() -> dict:
    failed = run_cmd(["systemctl", "--user", "--failed", "--no-legend", "--plain"])
    failed_units = []
    if failed["ok"]:
        for line in failed["stdout"].splitlines():
            unit = line.split(maxsplit=1)[0] if line.strip() else ""
            if unit:
                failed_units.append(unit)

    active = {}
    for unit in sorted(CRITICAL_UNITS):
        result = run_cmd(["systemctl", "--user", "is-active", unit])
        active[unit] = result["stdout"] or result.get("stderr") or "unknown"

    return {
        "failed_units": sorted(failed_units),
        "failed_check_error": None if failed["ok"] else (failed.get("stderr") or failed.get("error")),
        "critical_units": active,
    }


def parse_echo_state() -> dict:
    path = BASE / "memory/echo_state.json"
    if not path.exists():
        return {"exists": False, "critical": True, "reason": "missing"}
    try:
        data = json.loads(path.read_text())
        timestamp = data.get("timestamp")
        age_seconds = None
        if timestamp:
            ts = datetime.fromisoformat(timestamp).astimezone(timezone.utc)
            age_seconds = int((datetime.now(timezone.utc) - ts).total_seconds())
        return {
            "exists": True,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "system_health": data.get("system_health"),
            "failed_units": data.get("failed_units", {}),
            "cascade_error": data.get("cascade", {}).get("error") if isinstance(data.get("cascade"), dict) else None,
        }
    except Exception as exc:
        return {"exists": True, "critical": True, "reason": str(exc)}


def import_snapshot() -> dict:
    checks = {}
    for module, purpose in {**CORE_IMPORTS, **APP_IMPORTS}.items():
        checks[module] = {
            "available": importlib.util.find_spec(module) is not None,
            "purpose": purpose,
        }
    return checks


def venv_snapshot() -> list[dict]:
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    rows = []
    for cfg in sorted(BASE.glob("**/pyvenv.cfg")):
        if any(part in {".git", "__pycache__"} for part in cfg.parts):
            continue
        if cfg.parent.name not in {".venv", "venv"}:
            continue
        if len(cfg.relative_to(BASE).parts) > 5:
            continue
        text = cfg.read_text(errors="replace")
        version = None
        for line in text.splitlines():
            if line.startswith("version"):
                version = line.split("=", 1)[1].strip()
                break
        venv = cfg.parent
        py = venv / "bin/python"
        rows.append({
            "path": str(venv.relative_to(BASE)),
            "configured_version": version,
            "current_python": current,
            "python_exists": py.exists(),
            "may_need_rebuild": bool(version and not version.startswith(current)),
        })
    return rows


def file_sprawl_snapshot() -> dict:
    memory_files = [p for p in (BASE / "memory").glob("**/*") if p.is_file()]
    text_memory = [p for p in memory_files if p.suffix in {".txt", ".md", ".json", ".jsonl"}]
    active_text_memory = []
    for path in text_memory:
        rel = path.relative_to(BASE / "memory")
        if rel.parts and rel.parts[0] in ARCHIVAL_MEMORY_DIRS:
            continue
        active_text_memory.append(path)
    logs = [p for p in (BASE / "logs").glob("*") if p.is_file()] if (BASE / "logs").exists() else []
    big_logs = sorted(
        (
            {"path": str(p.relative_to(BASE)), "mb": round(p.stat().st_size / 1024 / 1024, 1)}
            for p in logs
            if p.stat().st_size > 100 * 1024 * 1024
        ),
        key=lambda item: item["mb"],
        reverse=True,
    )
    pycache_tags = {}
    for p in BASE.glob("core/__pycache__/*.pyc"):
        tag = p.name.split(".", 2)[1] if "." in p.name else "unknown"
        pycache_tags[tag] = pycache_tags.get(tag, 0) + 1
    return {
        "memory_file_count": len(memory_files),
        "text_memory_file_count": len(text_memory),
        "active_text_memory_file_count": len(active_text_memory),
        "archival_text_memory_file_count": len(text_memory) - len(active_text_memory),
        "archival_memory_dirs": sorted(ARCHIVAL_MEMORY_DIRS),
        "log_file_count": len(logs),
        "big_logs_over_100mb": big_logs[:10],
        "core_pycache_tags": pycache_tags,
    }


def generated_apps_snapshot() -> dict:
    apps_dir = BASE / "builds/apps"
    apps = []
    if apps_dir.exists():
        for meta in sorted(apps_dir.glob("*/echo_app.json")):
            try:
                data = json.loads(meta.read_text())
            except Exception:
                data = {}
            apps.append({
                "name": meta.parent.name,
                "status": data.get("status"),
                "deploy_error": data.get("deploy_error"),
            })
    by_status = {}
    for app in apps:
        key = app["status"] or "unknown"
        by_status[key] = by_status.get(key, 0) + 1
    return {
        "count": len(apps),
        "by_status": by_status,
        "with_deploy_error": [a for a in apps if a.get("deploy_error")][:20],
    }


def assess(report: dict) -> dict:
    critical = []
    warnings = []
    maintenance = []

    systemd = report["systemd"]
    for unit, state in systemd["critical_units"].items():
        if state != "active":
            critical.append(f"critical unit not active: {unit}={state}")
    for unit in systemd["failed_units"]:
        if unit in OPTIONAL_FAILED_UNITS:
            warnings.append(f"optional failed unit: {unit}")
        elif unit in DEFERRED_DELIVERY_UNITS and offsite_backup_transport_deferred():
            warnings.append(f"deferred offsite delivery: {unit}")
        elif unit.startswith("echo-") or unit.startswith("crow-"):
            critical.append(f"failed service: {unit}")

    state = report["echo_state"]
    if not state.get("exists"):
        critical.append("memory/echo_state.json missing")
    elif state.get("age_seconds") is not None and state["age_seconds"] > 900:
        critical.append(f"echo_state stale: {state['age_seconds']}s old")
    if state.get("cascade_error"):
        warnings.append(f"cascade snapshot error: {state['cascade_error']}")

    for module, check in report["imports"].items():
        if not check["available"]:
            warnings.append(f"missing python import: {module} ({check['purpose']})")

    for venv in report["venvs"]:
        if venv["may_need_rebuild"]:
            warnings.append(
                f"venv may need rebuild: {venv['path']} "
                f"configured={venv['configured_version']} current={venv['current_python']}"
            )

    sprawl = report["sprawl"]
    if sprawl["big_logs_over_100mb"]:
        warnings.append(f"large logs present: {len(sprawl['big_logs_over_100mb'])}")
    if sprawl["active_text_memory_file_count"] > 500:
        warnings.append(f"memory text sprawl: {sprawl['active_text_memory_file_count']} active text/json/md files")

    apps = report["generated_apps"]
    if apps["count"] > 50:
        maintenance.append(f"generated app inventory growth: {apps['count']} apps")
    if apps["with_deploy_error"]:
        maintenance.append(f"generated apps with deploy errors: {len(apps['with_deploy_error'])}")

    return {
        "status": "critical" if critical else ("warning" if warnings else "ok"),
        "critical": critical,
        "warnings": warnings,
        "maintenance": maintenance,
    }


def build_report() -> dict:
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "systemd": systemd_snapshot(),
        "echo_state": parse_echo_state(),
        "imports": import_snapshot(),
        "venvs": venv_snapshot(),
        "sprawl": file_sprawl_snapshot(),
        "generated_apps": generated_apps_snapshot(),
    }
    report["assessment"] = assess(report)
    return report


def write_report(report: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(f"{OUT.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.rename(OUT)
    summary = report["assessment"]
    line = (
        f"[{report['generated_at']}] status={summary['status']} "
        f"critical={len(summary['critical'])} warnings={len(summary['warnings'])}"
    )
    with LOG.open("a") as f:
        f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit nonzero on critical findings")
    parser.add_argument("--print", action="store_true", help="print the full JSON report")
    args = parser.parse_args()

    report = build_report()
    write_report(report)
    if args.print:
        print(json.dumps(report, indent=2))
    else:
        summary = report["assessment"]
        print(
            f"operational_audit: {summary['status']} "
            f"({len(summary['critical'])} critical, {len(summary['warnings'])} warnings)"
        )
        for item in summary["critical"][:5]:
            print(f"CRITICAL: {item}")
        for item in summary["warnings"][:5]:
            print(f"WARNING: {item}")
    return 1 if args.strict and report["assessment"]["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
