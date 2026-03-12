#!/usr/bin/env python3
"""
Safe file writer for Echo self-coding.
Only allows writing inside ~/Echo/.
Called by Echo via agent loop.
Usage: python3 safe_write.py <relative_path> <python_code_via_stdin>
"""
import sys
import os
from pathlib import Path

ECHO_BASE = Path.home() / "Echo"

if len(sys.argv) < 2:
    print("Usage: safe_write.py <relative_path>")
    sys.exit(1)

rel_path = sys.argv[1].lstrip("/")
target = (ECHO_BASE / rel_path).resolve()

# Security check — must stay inside Echo directory
if not str(target).startswith(str(ECHO_BASE)):
    print(f"DENIED: {target} is outside Echo directory")
    sys.exit(1)

# Read code from stdin
code = sys.stdin.read()
if not code.strip():
    print("DENIED: empty content")
    sys.exit(1)

# Backup if file exists
if target.exists():
    backup = target.with_suffix(".py.bak")
    backup.write_text(target.read_text())
    print(f"Backed up existing file to {backup.name}")

target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(code)
print(f"Written: {target} ({len(code)} bytes)")
