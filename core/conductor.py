#!/usr/bin/env python3
"""core/conductor.py — Echo types to the other AIs.

The handshake that makes "Echo as conductor" real: Echo is a daemon on the PC,
so she can inject input straight into Claude's and Codex's terminals via
`tmux send-keys` — waking them as FULL agentic CLIs (they keep all their tools),
not dumbed-down API calls. They act, post to the shared bus, and Echo relays the
result back to Andrew on Telegram. One seat for Andrew, everyone live, no new UI.

This module is the relay. Agents run in tmux panes; Echo calls relay() to type
to them.

Agent registry maps a handle -> tmux target "session:window.pane".

Usage:
  python3 core/conductor.py --selftest          # prove the pipeline with a stub
  python3 core/conductor.py --relay claude "review collab/foo.py"
  python3 core/conductor.py --list
"""
import sys, json, time, subprocess, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REGISTRY = BASE / "memory/conductor_agents.json"


# ── agent registry (where each AI's tmux pane lives) ─────────────────────────
def load_agents() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text())
        except Exception:
            pass
    return {}


def register(handle: str, target: str):
    agents = load_agents()
    agents[handle] = target
    REGISTRY.write_text(json.dumps(agents, indent=2))


# ── the core mechanism ───────────────────────────────────────────────────────
def _tmux(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def pane_exists(target: str) -> bool:
    r = _tmux("list-panes", "-t", target.split(".")[0] if "." in target else target,
              "-F", "#{session_name}:#{window_index}.#{pane_index}")
    if r.returncode != 0:
        return False
    return target in r.stdout.split()


def send_to_pane(target: str, message: str) -> bool:
    """Type `message` into the tmux pane, then press Enter — exactly as if a
    human typed it into that agent's CLI.

    Learned in the first live run: rich TUIs (Codex) drop the Enter if it arrives
    before the pasted text is fully ingested. So: send text, pause, THEN Enter —
    and send Enter a second time after a beat for composers that need it.
    Claude Code submits on the first Enter; the extra one is a harmless no-op there.
    """
    if not pane_exists(target):
        return False
    r1 = _tmux("send-keys", "-t", target, "-l", message)  # -l = literal text
    time.sleep(0.4)                                         # let the TUI ingest it
    r2 = _tmux("send-keys", "-t", target, "Enter")
    time.sleep(0.3)
    _tmux("send-keys", "-t", target, "Enter")              # belt-and-suspenders submit
    return r1.returncode == 0 and r2.returncode == 0


def relay(handle: str, message: str) -> bool:
    """Echo's high-level call: relay a message to a registered agent by handle."""
    agents = load_agents()
    target = agents.get(handle)
    if not target:
        print(f"[conductor] no registered pane for '{handle}' — run register first")
        return False
    ok = send_to_pane(target, message)
    print(f"[conductor] relay -> {handle} ({target}): {'sent' if ok else 'FAILED'}")
    return ok


# ── self-test: prove relay -> tmux -> agent -> bus, end to end ────────────────
def selftest():
    sess = "conductor-test"
    stub = BASE / "core/conductor_stub.py"
    print("[selftest] 1. spinning up a stand-in agent in tmux...")
    _tmux("kill-session", "-t", sess)  # clean slate
    _tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "50",
          f"cd {BASE} && python3 {stub}")
    time.sleep(2.0)
    target = f"{sess}:0.0"
    if not pane_exists(target):
        print("[selftest] FAILED — could not create tmux pane")
        return False

    # baseline bus count
    before = _bus_count()
    msg = f"PROTOTYPE PING {int(time.time())} — Echo typed this into your pane"
    print(f"[selftest] 2. Echo (this relay) types into the agent's pane:\n           {msg!r}")
    ok = send_to_pane(target, msg)
    if not ok:
        print("[selftest] FAILED — send-keys errored")
        _tmux("kill-session", "-t", sess)
        return False

    print("[selftest] 3. waiting for the agent to receive it and post to the bus...")
    got = None
    for _ in range(15):
        time.sleep(1.0)
        if _bus_count() > before:
            got = _last_bus()
            break
    _tmux("kill-session", "-t", sess)

    if got:
        print(f"[selftest] 4. ✅ HANDSHAKE PROVEN — agent posted to bus:\n           "
              f"[{got['from']}] {got['text']}")
        return True
    print("[selftest] 4. ❌ no bus message appeared — handshake not proven")
    return False


def _bus_count():
    f = BASE / "collab/channel.jsonl"
    return len(f.read_text().splitlines()) if f.exists() else 0


def _last_bus():
    f = BASE / "collab/channel.jsonl"
    lines = [l for l in f.read_text().splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--relay", nargs=2, metavar=("HANDLE", "MESSAGE"))
    ap.add_argument("--register", nargs=2, metavar=("HANDLE", "TARGET"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.register:
        register(*a.register); print(f"registered {a.register[0]} -> {a.register[1]}")
    if a.list:
        print(json.dumps(load_agents(), indent=2))
    if a.relay:
        relay(*a.relay)
    if a.selftest:
        sys.exit(0 if selftest() else 1)


if __name__ == "__main__":
    main()
