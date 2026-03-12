from __future__ import annotations
import os, re, sys, json, time
from pathlib import Path

ROOT = Path.cwd()

OUT = ROOT / "echo_bundle.txt"

# Keep it curated so it's usable by another AI
INCLUDE_FILES = [
    "echo.py",
    "echo_chat_main.py",
    "echo_chat_router_confirm.py",
    "events_reader.py",
    "file_watcher.py",
    "task_manager_v3.py",
    "echo_daemon_loop.py",
    "trading_bot.py",
    "echo_simple_agent.py",
    "core/executor.py",
    "core/self_act.py",
]

# Prefer canonical copies if present
PREFERRED_DIRS = ["app"]  # will pick app/<name> over root <name> when both exist

EXCLUDE_SUBSTRINGS = [
    "/venv/", "/.venv/", "/__pycache__/", "/.git/", "/node_modules/",
    "/backup_project/", "/logs/", "/memory/", "/docs/", "/chat/",
    "dirs_chunk_", "files_full_chunk_", "files_full_chunk", "screen_", ".png",
]

# Hard exclude sensitive files by name (expand as needed)
SENSITIVE_NAMES = {
    "appkey.txt", "keys.txt", "secret.txt", ".env", ".env.local",
    "robinhood_config.json",
}

# Max characters per file to avoid gigantic bundle
MAX_CHARS_PER_FILE = 40_000

def is_excluded(path: str) -> bool:
    s = path.replace("\\", "/")
    for sub in EXCLUDE_SUBSTRINGS:
        if sub in s:
            return True
    name = Path(path).name
    if name in SENSITIVE_NAMES:
        return True
    return False

def pick_path(rel: str) -> Path | None:
    # If the file exists in app/, prefer it
    r = Path(rel)
    if r.parts and r.parts[0] == "core":
        p = ROOT / rel
        return p if p.exists() else None

    for d in PREFERRED_DIRS:
        p = ROOT / d / r.name
        if p.exists():
            return p
    p2 = ROOT / rel
    if p2.exists():
        return p2
    return None

def safe_read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except Exception as e:
        return f"<<error reading {p}: {e}>>"

def tree(max_depth: int = 3) -> str:
    lines = []
    root_len = len(str(ROOT))
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = str(Path(dirpath))[root_len+1:] if len(str(Path(dirpath))) > root_len else "."
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirnames[:] = []
            continue
        # prune noisy dirs
        dirnames[:] = [d for d in dirnames if d not in ("venv",".venv",".git","__pycache__","node_modules","backup_project","logs","memory")]
        for f in sorted(filenames):
            rel = str(Path(rel_dir) / f) if rel_dir != "." else f
            if is_excluded(rel):
                continue
            if f.endswith((".py",".sh",".md",".json",".txt")):
                lines.append(rel)
    return "\n".join(lines[:800]) + ("\n... (tree truncated)" if len(lines) > 800 else "")

def main():
    header = f"""ECHO BUNDLE
Generated: {time.ctime()}
Root: {ROOT}

CURRENT CANONICAL TRUTH STORES (typical):
- events: echo_events.ndjson (echo_memory.json is a symlink to it for legacy compatibility)
- tasks:  echo_tasks.ndjson
- chat:   echo_chat_memory_v2.json
- capsules/executor state: echo_capsules.json

NOTE: This bundle is curated and excludes venv, logs, screenshots, backups, and likely secrets.
"""
    parts = [header, "\n=== PROJECT TREE (shallow) ===\n", tree(3), "\n\n=== FILES ===\n"]

    missing = []
    for rel in INCLUDE_FILES:
        p = pick_path(rel)
        if not p:
            missing.append(rel)
            continue
        rel_show = str(p.relative_to(ROOT))
        if is_excluded(rel_show):
            parts.append(f"\n\n===== FILE: {rel_show} (SKIPPED: excluded) =====\n")
            continue
        txt = safe_read(p)
        if len(txt) > MAX_CHARS_PER_FILE:
            txt = txt[:MAX_CHARS_PER_FILE] + "\n\n<<truncated>>\n"
        parts.append(f"\n\n===== FILE: {rel_show} =====\n{txt}")

    if missing:
        parts.append("\n\n=== MISSING REQUESTED FILES ===\n" + "\n".join(missing) + "\n")

    OUT.write_text("\n".join(parts))
    print(f"Wrote bundle: {OUT} ({OUT.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
