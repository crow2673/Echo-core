"""
core/command_handler.py
Command handler for Echo core daemon.
"""
from __future__ import annotations
import json
from pathlib import Path
from core.self_awareness import (
    build_self_awareness_block,
    get_system_snapshot,
    get_echo_process_state,
    get_echo_dir_summary,
)

EVENTS_FILE = Path("echo_events.ndjson")


def _tail_events(n: int) -> list[dict]:
    if n <= 0:
        return []
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(errors="ignore").splitlines()
    tail = lines[-n:]
    out = []
    for ln in tail:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def handle_command(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "(no command text provided)"

    low = text.lower().strip()

    # status / self-awareness
    if low in ("status", "self", "snapshot", "whoami", "sysinfo"):
        return build_self_awareness_block()

    # system details
    if low in ("system", "sysdetail", "resources"):
        snap = get_system_snapshot()
        lines = [
            f"CPU: {snap['cpu_percent']}% ({snap['cpu_count']} cores)",
            f"RAM: {snap['ram_used_gb']}/{snap['ram_total_gb']}GB ({snap['ram_percent']}%)",
            f"Disk: {snap['disk_used_gb']}/{snap['disk_total_gb']}GB ({snap['disk_percent']}%)",
            f"Uptime: {snap['uptime_hours']}h",
            f"Load: {snap.get('load_1m', '?')} (1m)",
        ]
        if snap.get("gpu_mem_used_mb"):
            lines.append(
                f"GPU: {snap['gpu_name']} "
                f"{snap['gpu_mem_used_mb']}/{snap['gpu_mem_total_mb']}MB "
                f"({snap['gpu_util_percent']}% util)"
            )
        return "\n".join(lines)

    # process state
    if low in ("processes", "procs", "ps"):
        procs = get_echo_process_state()
        lines = [
            f"echo_daemon: {'RUNNING (pid ' + str(procs['echo_daemon_pid']) + ')' if procs['echo_daemon'] else 'DOWN'}",
            f"ollama: {'UP' if procs['ollama'] else 'DOWN'}",
            f"yagna: {'UP' if procs['yagna'] else 'DOWN'}",
            f"ya_provider: {'UP' if procs['ya_provider'] else 'DOWN'}",
        ]
        if procs["ollama_models"]:
            lines.append(f"Ollama models loaded: {', '.join(procs['ollama_models'])}")
        return "\n".join(lines)

    # echo dir summary
    if low in ("files", "dir", "echo dir"):
        echo = get_echo_dir_summary()
        lines = [
            f"Total files: {echo['total_files']}",
            f"Python files: {echo['python_files']}",
            f"Capsule queue entries: {echo['memory_entries']}",
            f"Key files present: {', '.join(echo['key_files_present'])}",
        ]
        return "\n".join(lines)

    # changes N  -> summarize last N file_change events
    if low.startswith("changes"):
        parts = text.split()
        n = 10
        if len(parts) >= 2:
            try:
                n = int(parts[1])
            except Exception:
                n = 10
        evs = _tail_events(max(1, min(n, 200)))
        if not evs:
            return "(no events found in echo_events.ndjson)"
        fc = [e for e in evs if e.get("type") == "file_change"]
        if not fc:
            return f"(no file_change events in last {n} lines)"
        lines = []
        for e in fc:
            op = e.get("op", "?")
            path = e.get("path", "?")
            lines.append(f"- {op}: {path}")
        return "Recent file changes:\n" + "\n".join(lines[-n:])

    # default
    return f"[command acknowledged] {text}"
