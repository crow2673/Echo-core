#!/usr/bin/env python3
"""core/conductor_stub.py — a stand-in agent for the conductor handshake test.

Plays the role a real CLI agent (Claude/Codex) plays in the prototype: it sits
in a tmux pane, and whatever gets typed into that pane (by Echo via send-keys)
it receives on stdin and posts to the bus — proving the wake→act→bus pipeline
without disturbing the live Claude/Codex sessions.
"""
import sys, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
# play whichever agent name is passed (default claude-stub) so the conduct loop
# can match the reply to the handle it relayed to.
SENDER = sys.argv[1] if len(sys.argv) > 1 else "claude-stub"

print(f"[stub:{SENDER}] stand-in agent ready in tmux pane; listening for typed input...", flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if line == "__quit__":
        break
    # react exactly as a woken agent would: do something + report on the bus
    subprocess.run(
        ["python3", str(BASE / "collab/bus.py"), "send", SENDER,
         f"[WOKEN] received via Echo's relay: \"{line}\""],
        cwd=str(BASE), check=False,
    )
