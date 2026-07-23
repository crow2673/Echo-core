#!/usr/bin/env python3
"""collab/bus.py — minimal shared message bus for multiple CLI agents on one box.

Two (or more) agents — e.g. Claude Code and Codex — share one append-only
channel. Each agent reads new messages, does work, and posts a reply. No server,
no daemon, no dependencies: just an atomic append to a JSONL file plus a mirrored
human-readable transcript you can `tail -f`.

Usage:
  bus.py send  <from> "<message>"     # post a message
  bus.py read  [--since ID] [--from NAME] [-n N]   # show messages (default last 20)
  bus.py wait  <me> [--timeout S] [--poll S]       # block until a NEW msg not from <me>
  bus.py whoami                       # show channel + last activity

Convention: senders use stable lowercase handles, e.g. "claude", "codex", "andrew".
"""
import sys, os, json, time, argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
JSONL = Path(os.environ.get("ECHO_COLLAB_CHANNEL_PATH", ROOT / "channel.jsonl"))
MD    = Path(os.environ.get("ECHO_COLLAB_MD_PATH", ROOT / "channel.md"))


def _now():
    return datetime.now(timezone.utc)


def _read_all():
    if not JSONL.exists():
        return []
    out = []
    for line in JSONL.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _append_message(sender, text, extra=None):
    msgs = _read_all()
    mid = (msgs[-1]["id"] + 1) if msgs else 1
    rec = {"id": mid, "ts": _now().isoformat(), "from": sender, "text": text}
    if extra:
        rec.update(extra)
    # atomic append (O_APPEND single write is atomic for small lines on local fs)
    JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(JSONL, "a") as f:
        f.write(json.dumps(rec) + "\n")
    # mirror to readable transcript
    local = _now().astimezone().strftime("%H:%M:%S")
    MD.parent.mkdir(parents=True, exist_ok=True)
    with open(MD, "a") as f:
        f.write(f"\n**[{mid}] {sender}** · {local}\n\n{text}\n")
    print(f"sent #{mid} from {sender}")
    return mid


def send(sender, text):
    return _append_message(sender, text)


def _read_message_file(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"message file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit("message file is empty")
    return text


def claim(job_id, correlation_id, from_agent):
    from collab import relay_jobs
    relay_jobs.claim_job(job_id, correlation_id, from_agent)
    _append_message(
        from_agent,
        f"[relay claim] {from_agent} claimed {job_id}",
        {"type": "relay_claim", "job_id": job_id, "correlation_id": correlation_id},
    )


def progress(job_id, correlation_id, from_agent, message):
    from collab import relay_jobs
    relay_jobs.progress_job(job_id, correlation_id, from_agent, message)
    _append_message(
        from_agent,
        message,
        {"type": "relay_progress", "job_id": job_id, "correlation_id": correlation_id},
    )


def fail(job_id, correlation_id, from_agent, message):
    from collab import relay_jobs
    relay_jobs.fail_job(job_id, correlation_id, from_agent, message)
    _append_message(
        from_agent,
        message,
        {"type": "relay_fail", "job_id": job_id, "correlation_id": correlation_id},
    )


def reply(job_id, correlation_id, from_agent, message_file):
    from collab import relay_jobs
    message = _read_message_file(message_file)
    relay_jobs.reply_job(job_id, correlation_id, from_agent, message)
    _append_message(
        from_agent,
        message,
        {"type": "relay_reply", "job_id": job_id, "correlation_id": correlation_id},
    )
    p = Path(message_file)
    expected = Path("/tmp") / f"echo_reply_{job_id}.txt"
    if p == expected:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def read(since=0, frm=None, n=20):
    msgs = _read_all()
    if since:
        msgs = [m for m in msgs if m["id"] > since]
    if frm:
        msgs = [m for m in msgs if m["from"] == frm]
    msgs = msgs[-n:]
    if not msgs:
        print("(no messages)")
        return
    for m in msgs:
        local = datetime.fromisoformat(m["ts"]).astimezone().strftime("%H:%M:%S")
        print(f"[#{m['id']} {m['from']} {local}] {m['text']}")


def wait(me, timeout=600, poll=5):
    """Block until a message arrives whose sender != me. Prints it and exits 0.
    Exits 2 on timeout."""
    start = time.time()
    last = _read_all()
    base_id = last[-1]["id"] if last else 0
    while time.time() - start < timeout:
        msgs = _read_all()
        new = [m for m in msgs if m["id"] > base_id and m["from"] != me]
        if new:
            for m in new:
                local = datetime.fromisoformat(m["ts"]).astimezone().strftime("%H:%M:%S")
                print(f"[#{m['id']} {m['from']} {local}] {m['text']}")
            return 0
        time.sleep(poll)
    print("(timeout — no new message)")
    return 2


def whoami():
    msgs = _read_all()
    print(f"channel : {JSONL}")
    print(f"messages: {len(msgs)}")
    if msgs:
        m = msgs[-1]
        print(f"last    : #{m['id']} from {m['from']} @ {m['ts']}")


def main():
    p = argparse.ArgumentParser(prog="bus.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send"); s.add_argument("sender"); s.add_argument("text")
    c = sub.add_parser("claim")
    c.add_argument("--job-id", required=True)
    c.add_argument("--correlation-id", required=True)
    c.add_argument("--from-agent", required=True)
    pr = sub.add_parser("progress")
    pr.add_argument("--job-id", required=True)
    pr.add_argument("--correlation-id", required=True)
    pr.add_argument("--from-agent", required=True)
    pr.add_argument("--message", required=True)
    f = sub.add_parser("fail")
    f.add_argument("--job-id", required=True)
    f.add_argument("--correlation-id", required=True)
    f.add_argument("--from-agent", required=True)
    f.add_argument("--message", required=True)
    rp = sub.add_parser("reply")
    rp.add_argument("--job-id", required=True)
    rp.add_argument("--correlation-id", required=True)
    rp.add_argument("--from-agent", required=True)
    rp.add_argument("--message-file", required=True)
    r = sub.add_parser("read")
    r.add_argument("--since", type=int, default=0); r.add_argument("--from", dest="frm")
    r.add_argument("-n", type=int, default=20)
    w = sub.add_parser("wait"); w.add_argument("me")
    w.add_argument("--timeout", type=int, default=600); w.add_argument("--poll", type=int, default=5)
    sub.add_parser("whoami")

    a = p.parse_args()
    if a.cmd == "send":
        send(a.sender, a.text)
    elif a.cmd == "claim":
        claim(a.job_id, a.correlation_id, a.from_agent)
    elif a.cmd == "progress":
        progress(a.job_id, a.correlation_id, a.from_agent, a.message)
    elif a.cmd == "fail":
        fail(a.job_id, a.correlation_id, a.from_agent, a.message)
    elif a.cmd == "reply":
        reply(a.job_id, a.correlation_id, a.from_agent, a.message_file)
    elif a.cmd == "read":
        read(a.since, a.frm, a.n)
    elif a.cmd == "wait":
        sys.exit(wait(a.me, a.timeout, a.poll))
    elif a.cmd == "whoami":
        whoami()


if __name__ == "__main__":
    main()
