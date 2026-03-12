#!/usr/bin/env python3
"""Regenerate echo_contract.json with current state."""
import json, subprocess, sqlite3, hashlib
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"

def md5(path):
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()
    except:
        return "missing"

def memory_count():
    try:
        c = sqlite3.connect(str(BASE / "echo_semantic_memory.sqlite"))
        n = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        c.close()
        return n
    except:
        return 0

existing = json.loads((BASE / "echo_contract.json").read_text())
existing["updated_at"] = datetime.now().isoformat()
existing["memory"]["total_memories"] = memory_count()
existing["memory"]["memory_db_hash"] = md5(BASE / "echo_semantic_memory.sqlite")
existing["identity"]["modelfile_hash"] = md5(BASE / "Echo.Modelfile")

(BASE / "echo_contract.json").write_text(json.dumps(existing, indent=2))
print(f"Contract updated: {memory_count()} memories, {datetime.now().strftime('%Y-%m-%d %H:%M')}")
