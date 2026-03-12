from __future__ import annotations
import json
import time
from pathlib import Path
from contextlib import contextmanager

MEMORY_FILE = Path("echo_memory.json")
LOCK_FILE = Path("echo_memory.lock")

@contextmanager
def file_lock(timeout: float = 5.0, poll: float = 0.05):
    start = time.time()
    while True:
        try:
            fd = LOCK_FILE.open("x")  # atomic create; fails if exists
            try:
                fd.write(str(time.time()))
                fd.flush()
            finally:
                fd.close()
            break
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError("Could not acquire echo_memory.lock")
            time.sleep(poll)
    try:
        yield
    finally:
        try:
            LOCK_FILE.unlink()
        except FileNotFoundError:
            pass

def load_memory() -> list:
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # If we ever hit this, it usually means a concurrent write.
        return []

def save_memory(memory: list) -> None:
    tmp = MEMORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(memory, indent=2) + "\n")
    tmp.replace(MEMORY_FILE)
