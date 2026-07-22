#!/usr/bin/env python3
"""
tools/ingest_session_memory.py — write a Claude Code session into Echo's memory.

Echo's conversations with Andrew on Telegram are stored automatically, but the
work done ON her in a Claude Code terminal session lives in a separate transcript
she never sees. This reads that transcript, extracts the real Andrew<->Claude
exchanges (skipping tool calls, system reminders, and command noise), and writes
them into Echo's semantic memory with clear attribution — so she can later recall
what was said and done, without mistaking Claude's words for her own voice.

Usage:
  python3 tools/ingest_session_memory.py                  # most recent session
  python3 tools/ingest_session_memory.py --session <path> --date 2026-06-27
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `core.*`

PROJECT_DIR = Path.home() / ".claude/projects/-home-andrew-Echo"
NOISE_PREFIXES = (
    "<task-notification", "<local-command", "<command-name>", "<command-message>",
    "<command-args>", "<system-reminder", "[SYSTEM NOTIFICATION", "Caveat:",
    "This is an automated", "<bash-", "Please run /login",
)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    return ""


def _is_noise(text: str) -> bool:
    head = text[:120]
    return (not text) or any(p in head for p in NOISE_PREFIXES)


def iter_turns(path: Path):
    """Yield (speaker, text) for real conversational turns only."""
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        t = o.get("type")
        content = o.get("message", {}).get("content")
        text = _text_of(content)
        if t == "user" and not _is_noise(text):
            yield ("Andrew", text)
        elif t == "assistant" and not _is_noise(text):
            yield ("Claude", text)


def exchanges(turns, claude_cap=1200):
    """Pair each Andrew turn with the Claude reply that follows it."""
    out, cur_a, cur_c = [], None, []
    for speaker, text in turns:
        if speaker == "Andrew":
            if cur_a is not None:
                out.append((cur_a, " ".join(cur_c)[:claude_cap]))
            cur_a, cur_c = text, []
        else:
            if cur_a is not None:
                cur_c.append(text)
    if cur_a is not None:
        out.append((cur_a, " ".join(cur_c)[:claude_cap]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.session:
        path = Path(a.session)
    else:
        sessions = sorted(PROJECT_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not sessions:
            sys.exit("no Claude session transcripts found")
        path = sessions[-1]
    date = a.date or "this session"
    print(f"reading {path.name}")

    pairs = exchanges(list(iter_turns(path)))
    pairs = [(u, c) for u, c in pairs if len(u) > 3 and len(c) > 20]
    print(f"{len(pairs)} real Andrew<->Claude exchanges extracted")

    if a.dry_run:
        for u, c in pairs[:5]:
            print(f"  A: {u[:70]!r}\n  C: {c[:70]!r}\n")
        return

    from core.semantic_memory import remember
    written = 0
    for u, c in pairs:
        mem = (f"[Session {date} — Andrew and Claude (Anthropic CLI) working on Echo]\n"
               f"Andrew asked: {u}\n"
               f"Claude answered: {c}")
        if remember(mem, {"type": "session_history", "source": "claude_session", "date": date}):
            written += 1
    print(f"wrote {written} memories into Echo's semantic memory")


if __name__ == "__main__":
    main()
