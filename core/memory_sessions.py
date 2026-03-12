#!/usr/bin/env python3
"""
core/memory_sessions.py
=======================
Echo session continuity layer.
Harvested from free_think.py (Eli) session summary pattern.

On startup: loads last session summary + recent exchanges as orientation.
On shutdown: asks the model to summarize what was worked on.
"""

from __future__ import annotations
from datetime import datetime, timezone


def build_wakeup_context(memory) -> str:
    """
    Build an orientation block for the system prompt on daemon startup.
    Pulls last session summary + recent exchanges from EchoMemory.
    Returns empty string if no prior history exists.
    """
    last = memory.get_last_session_summary()
    recent = memory.search("recent work session tasks", k=5)

    if not last and not recent:
        return ""

    lines = ["Context from last session:"]

    if last:
        lines.append(f"Last session ({last['created_at'][:10]}): {last['summary']}")
        lines.append("")

    if recent:
        lines.append("Recent exchanges:")
        for text, _, score in recent:
            if score < 0.25:
                continue
            lines.append(f"- {text[:200]}")

    return "\n".join(lines)


def generate_session_summary(call_ollama_fn, exchanges_this_session: list[str]) -> str | None:
    """
    Ask the model to summarize the current session.
    exchanges_this_session: list of "User: ...\nEcho: ..." strings from this run.
    Returns summary string or None on failure.
    """
    if not exchanges_this_session:
        return None

    recent_text = "\n\n".join(exchanges_this_session[-10:])  # last 10 exchanges max

    prompt = (
        f"Here are the most recent exchanges from this session:\n\n"
        f"{recent_text}\n\n"
        f"Write a brief summary (3-5 sentences) of what was worked on, "
        f"what was resolved, and what remains pending. "
        f"Write it as a note to your future self. Be concrete and specific."
    )

    system = (
        "You are Echo, Andrew's local AI assistant. "
        "Output must be English only. "
        "Write only the summary, no preamble."
    )

    try:
        return call_ollama_fn(
            prompt=prompt,
            model="qwen2.5:7b",
            timeout=120.0,
            system_prompt=system,
        )
    except Exception as e:
        return f"(session summary failed: {e})"
