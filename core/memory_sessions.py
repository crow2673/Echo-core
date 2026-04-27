#!/usr/bin/env python3
"""
core/memory_sessions.py
=======================
Echo session continuity layer.
Harvested from free_think.py (Eli) session summary pattern.

On startup: loads last session summary + recent exchanges as orientation.
On shutdown: asks the model to summarize what was worked on.
"""
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def get_last_session_summary():
    try:
        from core.memory_store import load_memory
        mem = load_memory()
        return mem.get("last_session_summary", "")
    except Exception:
        return ""


def search(memory, query, limit=5):
    exchanges = memory.get("exchanges", [])
    ql = query.lower()
    matches = [e for e in exchanges if ql in e.get("user", "").lower() or ql in e.get("echo", "").lower()]
    return matches[-limit:]


def build_wakeup_context(memory=None):
    """
    Build an orientation block for the system prompt on daemon startup.
    Pulls last session summary + recent exchanges from EchoMemory.
    Returns empty string if no prior history exists.
    """
    parts = []

    summary = get_last_session_summary()
    if summary:
        parts.append(f"Context from last session:\n{summary}")

    if memory:
        recent = search(memory, "recent work session tasks", limit=3)
        if recent:
            created_at = recent[-1].get("ts", "")
            if created_at:
                parts.append(f"Last session ({created_at[:10]}):")
            for e in recent[-2:]:
                parts.append(f"  User: {e.get('user','')[:80]}")

    return "\n".join(parts)


def generate_session_summary(exchanges_this_session, memory=None):
    """
    Ask the model to summarize the current session.
    exchanges_this_session: list of "User: ...\nEcho: ..." strings from this run.
    Returns summary string or None on failure.
    """
    if not exchanges_this_session:
        return None
    try:
        from core.providers.router import call_ollama
        text = "Here are the most recent exchanges from this session:\n\n"
        text += "\n".join(exchanges_this_session[-10:])
        text += "\n\nWrite a brief summary (3-5 sentences) of what was worked on, what was resolved, and what remains pending. Write it as a note to your future self. Be concrete and specific."
        return call_ollama(
            prompt=text,
            model="qwen2.5:7b",
            system_prompt="You are Echo, Andrew's local AI assistant. Output must be English only. Write only the summary, no preamble.",
            timeout=60,
        )
    except Exception:
        return None
