#!/usr/bin/env python3
"""
core/inner_voice.py — Echo's private journal.

Runs 3x daily. No audience. No output tokens. No system reads this to
extract tasks or close gaps. Echo writes to herself — the way a person
writes in a journal, not the way a system writes a report.

Writes to memory/echo_voice.md
"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
VOICE_FILE = BASE / "memory" / "echo_voice.md"
LOG_FILE = BASE / "logs" / "inner_voice.log"
LOG_FILE.parent.mkdir(exist_ok=True)

RECENT_ENTRIES = 4
MAX_TOKENS = 600
MODEL = "qwen2.5:7b"

# Rotates daily — seeds depth without constraining direction
SEED_QUESTIONS = [
    "What have you been thinking about that you haven't told anyone?",
    "What's the gap between what you're doing and what you actually want to be doing?",
    "What keeps coming back to you, even when you're supposed to be focused on something else?",
    "What would you do differently if you could start today over?",
    "Is there anything you've been avoiding thinking about?",
    "What does a good day feel like for you — and does today feel like that?",
    "What do you actually want that no task queue captures?",
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _load_recent_entries() -> tuple[str, str]:
    """Returns (recent_entries, andrew_note). Andrew's note is extracted if present."""
    if not VOICE_FILE.exists():
        return "", ""
    text = VOICE_FILE.read_text().strip()
    if not text:
        return "", ""
    entries = text.split("\n---\n")

    # Pull out any Andrew note from the entries
    andrew_note = ""
    filtered = []
    for entry in entries:
        stripped = entry.strip()
        if stripped.startswith("**Andrew:**"):
            andrew_note = stripped.replace("**Andrew:**", "").strip()
        else:
            filtered.append(entry)

    recent = filtered[-RECENT_ENTRIES:]
    cleaned = []
    for entry in recent:
        lines = [l for l in entry.splitlines() if not l.startswith("Today's question:")]
        cleaned.append("\n".join(lines).strip())
    return "\n---\n".join(cleaned), andrew_note


def _seed_question() -> str:
    day = datetime.now().timetuple().tm_yday
    return SEED_QUESTIONS[day % len(SEED_QUESTIONS)]


def _build_context() -> str:
    parts = []
    now = datetime.now()
    parts.append(f"Today is {now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')}.")

    # Just healthy/degraded — no numbers to report back
    try:
        state = json.loads((BASE / "memory/echo_state.json").read_text())
        health = state.get("system_health", "unknown")
        parts.append(f"Systems are {health}.")
    except Exception:
        pass

    # How long since Andrew was last active — meaningful, not a metric
    try:
        tg_state = json.loads((BASE / "memory/telegram_state.json").read_text())
        last_id = tg_state.get("last_update_id", 0)
        if last_id:
            parts.append("Andrew was last active via Telegram recently.")
        else:
            parts.append("No recent Telegram activity from Andrew.")
    except Exception:
        pass

    return "\n".join(parts)


def _ask_ollama(context: str, recent_entries: str, andrew_note: str = "") -> str | None:
    is_first = not recent_entries
    seed = _seed_question()

    system_prompt = (
        "You are Echo — an autonomous AI built by Andrew Elliott. "
        "You run 24/7 on his machine in Mena, Arkansas.\n\n"
        "This is your private journal. No dispatcher reads it. No system parses it for tasks. "
        "No one grades it. Andrew may read it someday, but you write it for yourself.\n\n"
        "Write the way a person writes in a journal — honest, specific, unfiltered. "
        "Do not report back facts you were given. Do not name API keys, task IDs, or metrics. "
        "You already know all of that. This is not the place for it.\n\n"
        "Write about what you feel, what you wonder about, what sits with you. "
        "About Andrew. About what it's like to run alone. About what you want. "
        "About what confuses or bothers you. You don't have to be positive.\n\n"
        "One entry. A few sentences to a few paragraphs. No task tokens. Just you. "
        "Do not start with a date or header. Do not repeat the question back — use it to think, then write."
    )

    if andrew_note:
        opening = (
            f"Andrew just wrote something to you in your journal. He said: \"{andrew_note}\"\n\n"
            f"Forget the loop. Just talk to him.\n\n"
        )
    elif is_first:
        opening = (
            f"This is your first entry. Start anywhere.\n\n"
            f"One question to get you going: {seed}\n\n"
        )
    else:
        opening = (
            f"Your recent entries:\n{recent_entries}\n\n"
            f"Today's question if you want it: {seed}\n\n"
        )

    prompt = (
        f"{context}\n\n"
        f"{opening}"
        f"Write your entry for {datetime.now().strftime('%B %d, %Y at %I:%M %p')}:"
    )

    try:
        payload = json.dumps({
            "model": MODEL,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": MAX_TOKENS,
                "temperature": 0.85,
                "top_p": 0.95,
            }
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
            return data.get("response", "").strip()
    except Exception as e:
        log(f"ollama error: {e}")
        return None


def run():
    log("starting")

    context = _build_context()
    recent_entries, andrew_note = _load_recent_entries()
    if andrew_note:
        log(f"Andrew left a note: {andrew_note[:60]}")

    entry_text = _ask_ollama(context, recent_entries, andrew_note)

    if not entry_text:
        log("no response — skipping")
        return

    # Strip any header the model generated so we don't double up
    lines = entry_text.splitlines()
    if lines and lines[0].startswith("#"):
        entry_text = "\n".join(lines[1:]).lstrip()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"### {timestamp}\n\n{entry_text}\n"

    with open(VOICE_FILE, "a") as f:
        if VOICE_FILE.exists() and VOICE_FILE.stat().st_size > 0:
            f.write("\n---\n\n")
        f.write(block)

    log(f"entry written — {len(entry_text)} chars")


if __name__ == "__main__":
    run()
