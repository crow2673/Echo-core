#!/usr/bin/env python3
"""
core/self_awareness.py
======================
Echo's self-awareness layer.
Provides real-time knowledge of the machine, running processes,
and Echo's own state. Used to enrich system prompts and answer
self-referential queries.
"""

from __future__ import annotations
import subprocess
import psutil
import os
from pathlib import Path
from datetime import datetime, timezone

ECHO_DIR = Path("/home/andrew/Echo")


def get_system_snapshot() -> dict:
    """
    Returns a dict with current machine state:
    CPU, RAM, GPU, disk, uptime, load.
    """
    snap = {}

    # CPU
    snap["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    snap["cpu_count"] = psutil.cpu_count()

    # RAM
    ram = psutil.virtual_memory()
    snap["ram_total_gb"] = round(ram.total / 1e9, 1)
    snap["ram_used_gb"] = round(ram.used / 1e9, 1)
    snap["ram_percent"] = ram.percent

    # Disk
    disk = psutil.disk_usage("/home/andrew")
    snap["disk_total_gb"] = round(disk.total / 1e9, 1)
    snap["disk_used_gb"] = round(disk.used / 1e9, 1)
    snap["disk_percent"] = disk.percent

    # GPU
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True, timeout=3
        ).strip()
        parts = [p.strip() for p in out.split(",")]
        snap["gpu_name"] = parts[0]
        snap["gpu_mem_used_mb"] = int(parts[1])
        snap["gpu_mem_total_mb"] = int(parts[2])
        snap["gpu_util_percent"] = int(parts[3])
    except Exception:
        snap["gpu_name"] = "RTX 3060"
        snap["gpu_mem_used_mb"] = None
        snap["gpu_util_percent"] = None

    # Uptime
    boot = psutil.boot_time()
    uptime_s = datetime.now().timestamp() - boot
    snap["uptime_hours"] = round(uptime_s / 3600, 1)

    # Load average
    try:
        load = os.getloadavg()
        snap["load_1m"] = round(load[0], 2)
        snap["load_5m"] = round(load[1], 2)
    except Exception:
        snap["load_1m"] = None

    return snap


def get_echo_process_state() -> dict:
    """
    Returns state of key Echo and related processes.
    """
    state = {
        "echo_daemon": False,
        "ollama": False,
        "yagna": False,
        "ya_provider": False,
        "echo_daemon_pid": None,
        "ollama_models": [],
    }

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "echo_core_daemon" in cmdline:
                state["echo_daemon"] = True
                state["echo_daemon_pid"] = proc.info["pid"]
            if "ollama" in cmdline.lower():
                state["ollama"] = True
            if "yagna service" in cmdline:
                state["yagna"] = True
            if "ya-provider" in cmdline:
                state["ya_provider"] = True
        except Exception:
            continue

    # Ollama models loaded
    try:
        out = subprocess.check_output(
            ["ollama", "list"], text=True, timeout=3
        ).strip().splitlines()
        state["ollama_models"] = [l.split()[0] for l in out[1:] if l.strip()]
    except Exception:
        pass

    return state


def get_echo_dir_summary() -> dict:
    """
    Returns a summary of ~/Echo/ contents.
    """
    summary = {
        "total_files": 0,
        "python_files": 0,
        "key_files_present": [],
        "memory_entries": None,
    }

    key_files = [
        "echo_core_daemon.py",
        "echo_memory_sqlite.py",
        "echo_memory.json",
        "echo_semantic_memory.sqlite",
        "core/memory_sessions.py",
        "core/command_handler.py",
        "core/memory_store.py",
    ]

    if ECHO_DIR.exists():
        all_files = list(ECHO_DIR.rglob("*"))
        summary["total_files"] = sum(1 for f in all_files if f.is_file())
        summary["python_files"] = sum(1 for f in all_files if f.suffix == ".py")
        summary["key_files_present"] = [
            f for f in key_files if (ECHO_DIR / f).exists()
        ]

    # Memory entry count
    try:
        import json
        mem_file = ECHO_DIR / "echo_memory.json"
        if mem_file.exists():
            data = json.loads(mem_file.read_text())
            summary["memory_entries"] = len(data) if isinstance(data, list) else 0
    except Exception:
        pass

    return summary


def build_self_awareness_block() -> str:
    """
    Build a compact self-awareness context block for injection
    into Echo's system prompt.
    """
    lines = ["[Echo Self-Awareness Snapshot]"]

    try:
        sys = get_system_snapshot()
        lines.append(
            f"System: CPU {sys['cpu_percent']}% | "
            f"RAM {sys['ram_used_gb']}/{sys['ram_total_gb']}GB ({sys['ram_percent']}%) | "
            f"Disk {sys['disk_used_gb']}/{sys['disk_total_gb']}GB | "
            f"Uptime {sys['uptime_hours']}h"
        )
        if sys.get("gpu_mem_used_mb"):
            lines.append(
                f"GPU: {sys['gpu_name']} | "
                f"{sys['gpu_mem_used_mb']}/{sys['gpu_mem_total_mb']}MB used | "
                f"{sys['gpu_util_percent']}% util"
            )
    except Exception as e:
        lines.append(f"System snapshot failed: {e}")

    try:
        procs = get_echo_process_state()
        status_parts = []
        status_parts.append(f"echo_daemon={'UP' if procs['echo_daemon'] else 'DOWN'}")
        status_parts.append(f"ollama={'UP' if procs['ollama'] else 'DOWN'}")
        status_parts.append(f"yagna={'UP' if procs['yagna'] else 'DOWN'}")
        status_parts.append(f"ya_provider={'UP' if procs['ya_provider'] else 'DOWN'}")
        lines.append("Processes: " + " | ".join(status_parts))
        if procs["ollama_models"]:
            lines.append(f"Ollama models: {', '.join(procs['ollama_models'])}")
    except Exception as e:
        lines.append(f"Process snapshot failed: {e}")

    try:
        echo = get_echo_dir_summary()
        lines.append(
            f"Echo dir: {echo['total_files']} files, "
            f"{echo['python_files']} .py | "
            f"capsule queue: {echo['memory_entries']} entries"
        )
    except Exception as e:
        lines.append(f"Echo dir snapshot failed: {e}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_self_awareness_block())
    print()
    print("--- Full system snapshot ---")
    import json
    print(json.dumps(get_system_snapshot(), indent=2))
    print("--- Process state ---")
    print(json.dumps(get_echo_process_state(), indent=2))
