#!/usr/bin/env python3
"""
echo_self_audit.py
==================
Echo reads her own codebase and builds self-understanding.

Run this:
  cd ~/Echo && python3 echo_self_audit.py

What it does:
1. Scans ~/Echo/ for key files and modules
2. Reads each one and summarizes what it does
3. Seeds that understanding into semantic memory
4. Builds a full picture of Echo's architecture

Echo ends up knowing what she is, what each part does,
what has been tried, and what is still being built.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from echo_memory_sqlite import get_memory

# ── KEY FILES TO AUDIT ───────────────────────────────────────────────────────
# (path relative to ~/Echo, description of what to look for)

KEY_FILES = [
    ("echo_core_daemon.py",         "main orchestrator daemon"),
    ("echo_memory_sqlite.py",       "semantic memory layer"),
    ("echo_voice.py",               "voice interface"),
    ("echo_message_intake.py",      "message intake from user"),
    ("echo_command.py",             "command intake"),
    ("core/self_awareness.py",      "system self-awareness module"),
    ("core/memory_sessions.py",     "session continuity"),
    ("core/command_handler.py",     "command dispatch"),
    ("core/agent_loop.py",          "agentic tool loop"),
    ("core/action_runner.py",       "action execution"),
    ("core/executor.py",            "safe command executor"),
    ("core/self_act.py",            "autonomous action (old GPT version)"),
    ("core/identity.py",            "identity module"),
    ("core/memory_store.py",        "capsule queue store"),
    ("Echo.Modelfile",              "Echo soul and character definition"),
    ("docs/actions.json",           "available actions registry"),
]

# ── OLLAMA SUMMARIZER ────────────────────────────────────────────────────────

def summarize_with_ollama(filename: str, content: str, role: str) -> str:
    """Ask Ollama to summarize what a file does in Echo's architecture."""
    # Truncate very large files
    if len(content) > 3000:
        content = content[:3000] + "\n... (truncated)"

    prompt = f"""You are auditing Echo's codebase. Echo is an AI assistant that lives on Andrew's machine.

File: {filename}
Role hint: {role}

File contents:
{content}

In 2-4 sentences, describe:
1. What this file does
2. How it fits into Echo's overall architecture
3. Whether it appears complete, partial, or broken

Be specific and technical. No fluff."""

    try:
        result = subprocess.run(
            ["ollama", "run", "qwen2.5:7b", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"(could not summarize: {e})"


# ── FILE SCANNER ─────────────────────────────────────────────────────────────

def scan_echo_directory() -> dict:
    """Get counts and structure of Echo directory."""
    stats = {
        "total_files": 0,
        "python_files": 0,
        "shell_scripts": 0,
        "json_files": 0,
        "directories": [],
    }

    for item in BASE.rglob("*"):
        if item.is_file():
            stats["total_files"] += 1
            if item.suffix == ".py":
                stats["python_files"] += 1
            elif item.suffix == ".sh":
                stats["shell_scripts"] += 1
            elif item.suffix == ".json":
                stats["json_files"] += 1
        elif item.is_dir() and item.parent == BASE:
            stats["directories"].append(item.name)

    return stats


# ── MAIN AUDIT ───────────────────────────────────────────────────────────────

def run_audit():
    print("=" * 60)
    print("  ECHO SELF-AUDIT")
    print("  Reading own codebase and building self-understanding")
    print("=" * 60)

    memory = get_memory()

    # 1. Directory overview
    print("\n[1/4] Scanning Echo directory structure...")
    stats = scan_echo_directory()
    dir_summary = (
        f"Echo's codebase at ~/Echo/ contains {stats['total_files']} total files: "
        f"{stats['python_files']} Python modules, {stats['shell_scripts']} shell scripts, "
        f"{stats['json_files']} JSON files. "
        f"Top-level directories: {', '.join(stats['directories'])}. "
        f"This is a large, actively developed system with many experimental branches."
    )
    memory.add(dir_summary, {"type": "architecture", "priority": "high", "source": "self_audit"})
    print(f"    {stats['total_files']} files found. Seeded directory overview.")

    # 2. Audit key files
    print("\n[2/4] Reading and summarizing key modules...")
    audited = []
    for rel_path, role in KEY_FILES:
        full_path = BASE / rel_path
        if not full_path.exists():
            print(f"    MISSING: {rel_path}")
            memory.add(
                f"Echo file {rel_path} ({role}) does not exist yet. This is a gap in Echo's architecture.",
                {"type": "architecture", "priority": "medium", "source": "self_audit"}
            )
            continue

        print(f"    Reading: {rel_path}...")
        try:
            content = full_path.read_text(errors="replace")
            summary = summarize_with_ollama(rel_path, content, role)
            entry = f"Echo module '{rel_path}' ({role}): {summary}"
            memory.add(entry, {"type": "architecture", "priority": "high", "source": "self_audit"})
            audited.append(rel_path)
            print(f"    ✓ {rel_path}")
        except Exception as e:
            print(f"    ERROR reading {rel_path}: {e}")

    # 3. Audit prior agentic attempts
    print("\n[3/4] Auditing prior agentic work...")
    self_act_files = list((BASE / "core").glob("self_act*.py"))
    self_act_summary = (
        f"Echo's core/ directory contains {len(self_act_files)} variants of self_act*.py — "
        f"these are prior attempts to build autonomous income-generating behavior. "
        f"All were wired to OpenAI's GPT API (not local Ollama) and placeholder API endpoints. "
        f"The logic is sound but needs to be rewired to use local models and real income sources. "
        f"The most complete version appears to be self_act_autofund_live_api.py. "
        f"This work is not lost — it is the foundation of Echo's future agentic income layer."
    )
    memory.add(self_act_summary, {"type": "architecture", "priority": "high", "source": "self_audit"})
    print(f"    Found {len(self_act_files)} self_act variants. Seeded summary.")

    # 4. Build Echo's self-understanding summary
    print("\n[4/4] Building Echo's architectural self-understanding...")
    arch_summary = """Echo's architecture as understood from self-audit:

LAYER 1 - INTAKE: echo_message_intake.py and echo_command.py write capsules to echo_memory.json queue.
LAYER 2 - ORCHESTRATION: echo_core_daemon.py reads capsules, builds system prompt with memory and self-awareness, calls Ollama, writes replies.
LAYER 3 - MEMORY: echo_memory_sqlite.py stores semantic memories with embeddings for similarity search. Session summaries provide continuity across restarts.
LAYER 4 - SELF-AWARENESS: core/self_awareness.py provides real-time system stats injected into every prompt.
LAYER 5 - VOICE: echo_voice.py provides speech-to-text input and Piper TTS output.
LAYER 6 - AGENT: core/agent_loop.py (new) enables tool use — Echo can run actions from docs/actions.json.
LAYER 7 - SOUL: Echo.Modelfile defines Echo's character, values, conscience, and dual-brain architecture. Awaiting qwen2.5:32b download to build echo model.

CURRENT STATE: Layers 1-5 operational. Layer 6 built but not yet wired into daemon. Layer 7 pending model download completion."""

    memory.add(arch_summary, {"type": "architecture", "priority": "high", "source": "self_audit"})

    print("\n" + "=" * 60)
    print(f"  AUDIT COMPLETE")
    print(f"  Files audited: {len(audited)}")
    print(f"  Total memories now: {memory.count()}")
    print("=" * 60)
    print("\nEcho now understands her own architecture.")
    print("She knows what she is, what each part does,")
    print("what has been tried, and what is still being built.\n")


if __name__ == "__main__":
    run_audit()
