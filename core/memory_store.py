#!/usr/bin/env python3
"""core/memory_store.py — Echo's flat-file memory layer."""
import contextlib
import json
import time
from pathlib import Path

MEMORY_FILE = Path.home() / "Echo/echo_memory.json"
LOCK_FILE = Path.home() / "Echo/echo_memory.lock"


@contextlib.contextmanager
def file_lock(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fd = LOCK_FILE.open("x")
            fd.write(str(time.time()))
            fd.close()
            try:
                yield
            finally:
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass
            return
        except FileExistsError:
            time.sleep(0.1)
    raise TimeoutError("Could not acquire echo_memory.lock")


def load_memory():
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return {"exchanges": [], "capsules": []}
    try:
        data = json.loads(MEMORY_FILE.read_text())
        # Legacy format: flat list of capsules
        if isinstance(data, list):
            return {"exchanges": [], "capsules": data}
        return data
    except Exception:
        return {"exchanges": [], "capsules": []}


def save_memory(data):
    tmp = MEMORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(MEMORY_FILE)


def get_memory():
    return load_memory()


def store_exchange(user_text, echo_text, memory=None):
    with file_lock():
        mem = memory or load_memory()
        mem.setdefault("exchanges", []).append({
            "user": user_text,
            "echo": echo_text,
            "ts": __import__("datetime").datetime.now().isoformat(),
        })
        if len(mem["exchanges"]) > 200:
            mem["exchanges"] = mem["exchanges"][-200:]
        save_memory(mem)
