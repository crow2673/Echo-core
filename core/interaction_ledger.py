#!/usr/bin/env python3
"""core/interaction_ledger.py — Echo's memory of her conversation with Andrew.

The problem this fixes (found 2026-06-11 by the Claude+Codex+Echo audit):
Telegram freeform was STATELESS — every message hit the model with zero prior
turns, was written only to a fine-tune file, and Andrew's corrections
("that's fabricated", "getting worse not better") were captured nowhere and
trained the model exactly as hard as good replies. So Andrew kept reaching for
a continuous companion and hitting a thing that forgot the last sentence.

This is the durable conversation layer. Every turn (Andrew + Echo) is recorded,
typed, and — when Andrew corrects or praises — captured as LABELED feedback so
his richest signal stops evaporating.

Public API (frozen — other modules build against this):
    record(role, text, kind=None, meta=None) -> dict
    classify(text) -> 'command'|'approval'|'correction'|'conversation'
    polarity(text) -> -1 | 0 | +1
    recent(n=20) -> list[turn]
    context_block(n=15) -> str          # ready to inject into an LLM prompt
    last_andrew() -> turn | None
"""
import os, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LEDGER = BASE / "memory/interaction_ledger.jsonl"
TELEGRAM_CHAT_ID_FILE = Path.home() / ".config/echo/telegram_chat_id"

# ── classification heuristics ────────────────────────────────────────────────
# /approve|/reject anywhere at start, OR a SHORT standalone yes/no — not any
# sentence that merely begins with "no" (e.g. "No new task just you, im chatting").
_APPROVAL = re.compile(
    r"^\s*(/?(approve|reject)\b"                                   # command form
    r"|(yes|no|y|n|yep|nope|yeah|nah|approved|denied|do it|go ahead|sounds good)"
    r"\s*[.!]?\s*$)", re.I)                                        # bare/standalone only
_COMMAND  = re.compile(r"^\s*/\w+")
# Andrew correcting/calling out a bad or dishonest reply
_CORRECTION = re.compile(
    r"\b(wrong|fabricat\w*|hallucinat\w*|not (honest|true|fully|what)|that'?s not|"
    r"getting worse|incorrect|you forgot|completely (wrong|off|fabricated)|stop (listing|telling)|"
    r"still (broken|wrong|not)|didn'?t|doesn'?t|never (said|asked)|isn'?t (true|accurate|right)|"
    r"that is completely|o really|made up)\b", re.I)
_POS = re.compile(r"\b(good|nice|perfect|great|exactly|well done|better|love it|that'?s (it|right)|correct|thank)\b", re.I)


def _now():
    return datetime.now(timezone.utc).isoformat()


def classify(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "conversation"
    if _COMMAND.match(t):
        return "command"
    if _APPROVAL.match(t):
        return "approval"
    if _CORRECTION.search(t):
        return "correction"
    return "conversation"


def polarity(text: str) -> int:
    """-1 = Andrew is unhappy/correcting, +1 = approving, 0 = neutral."""
    t = text or ""
    if _CORRECTION.search(t):
        return -1
    if _POS.search(t):
        return 1
    return 0


def _read():
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _append(turn):
    with open(LEDGER, "a") as f:
        f.write(json.dumps(turn) + "\n")


def record(role: str, text: str, kind: str = None, meta: dict = None) -> dict:
    """Record one conversation turn. role='andrew'|'echo'.
    Andrew's corrections/praise are also logged as LABELED feedback so they
    stop evaporating into unlabeled fine-tune data."""
    existing = _read()
    tid = (existing[-1]["id"] + 1) if existing else 1
    role = (role or "").lower()
    if kind is None:
        kind = classify(text) if role == "andrew" else "reply"
    turn = {"id": tid, "ts": _now(), "role": role, "kind": kind,
            "text": text, "meta": meta or {}}
    _append(turn)

    # capture Andrew's feedback as a real, LABELED signal
    if role == "andrew":
        pol = polarity(text)
        if pol != 0:
            _log_feedback(text, pol, kind)
        if kind == "correction":
            prior_reply = next(
                (turn.get("text", "") for turn in reversed(existing) if turn.get("role") == "echo"),
                "",
            )
            try:
                from core.correction_memory import record_correction
                record_correction(text, prior_reply)
            except Exception:
                pass
    return turn


def _log_feedback(text, pol, kind):
    try:
        from core.event_ledger import log_event
        label = "andrew_correction" if pol < 0 else "andrew_praise"
        log_event("feedback", "interaction_ledger",
                  f"{label}: {text[:120]}", score=float(pol),
                  data={"label": label, "polarity": pol, "kind": kind})
    except Exception:
        pass


def recent(n: int = 20) -> list:
    return _read()[-n:]


def last_andrew():
    for t in reversed(_read()):
        if t["role"] == "andrew":
            return t
    return None


def context_block(n: int = 15) -> str:
    """Recent conversation, formatted for direct injection into an LLM prompt."""
    turns = recent(n)
    if not turns:
        return "(no prior conversation on record)"
    lines = ["=== recent conversation with Andrew (most recent last) ==="]
    for t in turns:
        who = "Andrew" if t["role"] == "andrew" else "Echo"
        tag = f" [{t['kind']}]" if t["kind"] in ("correction", "approval", "command") else ""
        lines.append(f"{who}{tag}: {t['text']}")
    return "\n".join(lines)


# ── one-time backfill from existing telegram logs ────────────────────────────
def _configured_telegram_chat_id() -> str | None:
    """Return the configured Telegram chat id for identity-specific backfill."""
    raw = ""
    try:
        if TELEGRAM_CHAT_ID_FILE.exists():
            raw = TELEGRAM_CHAT_ID_FILE.read_text().strip()
    except OSError:
        raw = ""
    if not raw:
        raw = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not re.fullmatch(r"-?\d+", raw or ""):
        return None
    return raw


def backfill_from_telegram():
    """Seed the ledger from historical telegram_intake logs so Echo starts with
    real conversation history instead of a blank slate."""
    import glob
    chat_id = _configured_telegram_chat_id()
    if not chat_id:
        return 0
    from_line = re.compile(rf"from {re.escape(chat_id)}:\s*(.+)$")
    msgs = []
    for path in glob.glob(str(BASE / "logs/telegram_intake.log*")):
        for line in Path(path).read_text(errors="ignore").splitlines():
            m = from_line.search(line)
            if m:
                # try to grab a leading timestamp
                ts = None
                tm = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if tm:
                    ts = tm.group(1)
                msgs.append((ts, m.group(1).strip()))
    # collapse consecutive identical text (the log double-prints each line)
    uniq, prev = [], None
    for ts, txt in msgs:
        if txt == prev:
            continue
        uniq.append((ts, txt))
        prev = txt
    # historical seeding: write turns directly WITHOUT firing live feedback events
    n = 0
    for ts, txt in uniq:
        existing = _read()
        tid = (existing[-1]["id"] + 1) if existing else 1
        _append({"id": tid, "ts": _now(), "role": "andrew",
                 "kind": classify(txt), "text": txt,
                 "meta": {"source": "telegram_backfill", "orig_ts": ts}})
        n += 1
    return n


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        print(f"backfilled {backfill_from_telegram()} Andrew messages")
    if a.stats:
        turns = _read()
        from collections import Counter
        kinds = Counter(t["kind"] for t in turns if t["role"] == "andrew")
        print(f"total turns: {len(turns)} | andrew kinds: {dict(kinds)}")
    if a.show:
        print(context_block(a.show))
