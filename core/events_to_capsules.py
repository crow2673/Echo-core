#!/usr/bin/env python3
"""core/events_to_capsules.py — converts echo_events.ndjson entries into capsules."""
import json
from datetime import datetime, timezone
from pathlib import Path

EVENTS_FILE = Path.home() / "Echo/echo_events.ndjson"
CURSOR_FILE = Path.home() / "Echo/memory/events_cursor.json"
MAX_LINES = 50


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_cursor():
    if CURSOR_FILE.exists():
        try:
            return json.loads(CURSOR_FILE.read_text()).get("offset", 0)
        except Exception:
            pass
    return 0


def save_cursor(offset):
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_FILE.write_text(json.dumps({"offset": offset}))


def tick(memory, max_lines=MAX_LINES):
    """Process new events from echo_events.ndjson, add relevant ones as capsules."""
    if not EVENTS_FILE.exists():
        return 0

    offset = load_cursor()
    lines = EVENTS_FILE.read_text().splitlines()
    new_lines = lines[offset:]

    if not new_lines:
        return 0

    added = 0
    capsules = memory.setdefault("capsules", [])
    existing_ids = {c.get("cap_id") for c in capsules}

    for i, line in enumerate(new_lines[:max_lines]):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue

        etype = event.get("type", "")
        if etype == "file_change":
            cap_id = f"EVENT:file_change:{offset + i}"
            if cap_id not in existing_ids:
                capsules.append({
                    "cap_id": cap_id,
                    "type": "event",
                    "text": f"File changed: {event.get('path', '?')}",
                    "status": "new",
                    "created_at": utcnow(),
                })
                added += 1

    save_cursor(offset + len(new_lines[:max_lines]))
    return added
