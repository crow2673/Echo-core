#!/usr/bin/env python3
import json
import time
import fnmatch
from pathlib import Path

EVENTS_FILE = Path("echo_events.ndjson")
STATE_FILE = Path("memory/file_watcher_state.json")

WATCH_DIRS = [Path("/home/andrew/Echo")]

# Keep this tight to reduce noise; expand later if you want
INCLUDE = ["*.py", "*.sh", "*.md"]

EXCLUDE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "node_modules", "memory",
    "backup_project",
}

# Critical: do not watch files that Echo itself writes/updates a lot
EXCLUDE_FILES = {
    "echo_events.ndjson",
    "echo_tasks.ndjson",
    "echo_capsules.json",
    "echo_chat_memory.json",
    "echo_chat_memory_v2.json",
    "daemon.log",
    "file_watcher.log",
    "echo_memory.json",          # symlink to events
    "echo_memory.legacy.ndjson", # old
}

POLL_SECONDS = 2.0

def match_any(name: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))

def append_event(obj: dict):
    obj.setdefault("ts", time.time())
    with EVENTS_FILE.open("a") as f:
        f.write(json.dumps(obj) + "\n")

def iter_files():
    for root in WATCH_DIRS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                if p.is_dir():
                    continue

                # ignore symlinks (prevents echo_memory.json -> echo_events.ndjson feedback)
                if p.is_symlink():
                    continue

                if p.name in EXCLUDE_FILES:
                    continue

                if any(part in EXCLUDE_DIRS for part in p.parts):
                    continue

                if not match_any(p.name, INCLUDE):
                    continue

                yield p
            except Exception:
                continue

def snapshot():
    snap = {}
    for p in iter_files():
        try:
            st = p.stat()
            snap[str(p)] = {"mtime": st.st_mtime, "size": st.st_size}
        except FileNotFoundError:
            continue
    return snap

def main():
    state = load_state()
    current = snapshot()

    # Baseline with no events
    if not state:
        save_state(current)
        print(f"File watcher initialized: tracking {len(current)} files")
    else:
        print(f"File watcher resumed: tracking {len(state)} files")

    while True:
        time.sleep(POLL_SECONDS)
        new = snapshot()

        for path, meta in new.items():
            prev = state.get(path)
            if prev is None:
                append_event({"type": "file_change", "op": "created", "path": path, **meta})
            else:
                if meta["mtime"] != prev.get("mtime") or meta["size"] != prev.get("size"):
                    append_event({"type": "file_change", "op": "modified", "path": path, **meta})

        for path in state.keys():
            if path not in new:
                append_event({"type": "file_change", "op": "deleted", "path": path})

        state = new
        save_state(state)

if __name__ == "__main__":
    main()
