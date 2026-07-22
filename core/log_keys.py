#!/usr/bin/env python3
"""Stable log-key extraction for Echo log anomaly detection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
MEMORY_DIR = BASE / "memory"
VOCAB_PATH = MEMORY_DIR / "log_key_vocab.json"
EVENTS_PATH = MEMORY_DIR / "log_key_events.jsonl"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
SYSLOG_TS_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HASH_RE = re.compile(r"\b[0-9a-fA-F]{12,64}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")
HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
PATH_RE = re.compile(r"(?<!\w)(?:~|/home/[^\s:]+|/tmp/[^\s:]+|/var/[^\s:]+|/run/[^\s:]+|/usr/[^\s:]+|/etc/[^\s:]+|/home/andrew/Echo/[^\s:]+)")
NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:%|ms|s|m|h|MB|GB|KiB|MiB|GiB)?\b")
PID_RE = re.compile(r"\[[0-9]+\]")
WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class LogEvent:
    ts: str
    source: str
    key: str
    template: str
    raw_hash: str
    raw: str

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "source": self.source,
            "key": self.key,
            "template": self.template,
            "raw_hash": self.raw_hash,
            "raw": self.raw,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_line(line: str) -> str:
    """Convert one noisy log line into a stable template string."""
    text = ANSI_RE.sub("", str(line or "").strip())
    text = ISO_TS_RE.sub("<TS>", text)
    text = SYSLOG_TS_RE.sub("<TS>", text)
    text = UUID_RE.sub("<UUID>", text)
    text = MAC_RE.sub("<MAC>", text)
    text = IPV4_RE.sub("<IP>", text)
    text = PATH_RE.sub("<PATH>", text)
    text = HEX_RE.sub("<HEX>", text)
    text = HASH_RE.sub("<HASH>", text)
    text = PID_RE.sub("[<PID>]", text)
    text = TIME_RE.sub("<TIME>", text)
    text = NUMBER_RE.sub("<NUM>", text)
    text = text.replace(str(BASE), "<BASE>")
    text = WS_RE.sub(" ", text).strip()
    return text or "<EMPTY>"


def key_for_template(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8", "replace")).hexdigest()[:12]


def raw_hash(line: str) -> str:
    return hashlib.sha256(str(line or "").encode("utf-8", "replace")).hexdigest()[:16]


def load_vocab(path: Path = VOCAB_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "templates": {}, "next_index": 1, "updated_at": None}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get("templates"), dict):
            _ensure_indices(data)
            return data
    except Exception:
        pass
    return {"version": 1, "templates": {}, "next_index": 1, "updated_at": None}


def _ensure_indices(vocab: dict) -> None:
    """Migrate older vocabs to persistent numeric ids; PAD=0 remains reserved."""
    templates = vocab.setdefault("templates", {})
    used = {
        int(item["index"])
        for item in templates.values()
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }
    next_index = max(used, default=0) + 1
    for key in sorted(templates):
        item = templates[key]
        if not isinstance(item, dict):
            templates[key] = {"template": str(item), "count": 0}
            item = templates[key]
        if not str(item.get("index", "")).isdigit():
            item["index"] = next_index
            next_index += 1
    vocab["next_index"] = max(int(vocab.get("next_index") or 1), next_index)


def save_vocab(vocab: dict, path: Path = VOCAB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_indices(vocab)
    vocab["updated_at"] = _utc_now()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(vocab, indent=2, sort_keys=True))
    tmp.rename(path)


def register_template(template: str, vocab: dict) -> str:
    _ensure_indices(vocab)
    key = key_for_template(template)
    templates = vocab.setdefault("templates", {})
    if key not in templates:
        templates[key] = {
            "template": template,
            "count": 0,
            "first_seen": _utc_now(),
            "index": int(vocab.get("next_index") or 1),
        }
        vocab["next_index"] = int(vocab.get("next_index") or 1) + 1
    item = templates[key]
    item["template"] = template
    item["count"] = int(item.get("count", 0)) + 1
    item["last_seen"] = _utc_now()
    return key


def event_from_line(line: str, source: str, vocab: dict, ts: str | None = None) -> LogEvent | None:
    raw = str(line or "").rstrip("\n")
    if not raw.strip():
        return None
    template = normalize_line(raw)
    key = register_template(template, vocab)
    return LogEvent(
        ts=ts or _extract_ts(raw) or _utc_now(),
        source=source,
        key=key,
        template=template,
        raw_hash=raw_hash(raw),
        raw=raw[:1000],
    )


def _extract_ts(line: str) -> str | None:
    match = ISO_TS_RE.search(line)
    if not match:
        return None
    raw = match.group(0).replace(" ", "T").replace(",", ".")
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []
    chunk_size = 8192
    chunks = []
    line_count = 0
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            pos = handle.tell()
            while pos > 0 and line_count <= max_lines:
                read_size = min(chunk_size, pos)
                pos -= read_size
                handle.seek(pos)
                chunk = handle.read(read_size)
                chunks.append(chunk)
                line_count += chunk.count(b"\n")
    except OSError:
        return []
    text = b"".join(reversed(chunks)).decode("utf-8", "replace")
    return text.splitlines()[-max_lines:]


def iter_file_events(
    vocab: dict,
    max_lines_per_file: int = 500,
    max_files: int = 80,
) -> Iterable[LogEvent]:
    if not LOG_DIR.exists():
        return
    paths = sorted(LOG_DIR.glob("*.log"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    if max_files > 0:
        paths = paths[:max_files]
    for path in paths:
        source = f"file:{path.name}"
        for line in tail_lines(path, max_lines_per_file):
            event = event_from_line(line, source, vocab)
            if event:
                yield event


def iter_journal_events(
    vocab: dict,
    since: str = "24 hours ago",
    max_lines: int = 3000,
    deadline_at: float | None = None,
) -> Iterable[LogEvent]:
    if deadline_at and time.monotonic() >= deadline_at:
        return
    cmd = ["journalctl", "--user", "-o", "short-iso", "--since", since, "--no-pager", "-q"]
    try:
        timeout = 30
        if deadline_at:
            timeout = max(1, min(timeout, int(deadline_at - time.monotonic())))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return
    if result.returncode != 0:
        return
    for line in result.stdout.splitlines()[-max_lines:]:
        source = _journal_source(line)
        event = event_from_line(line, source, vocab)
        if event:
            yield event


def _journal_source(line: str) -> str:
    # short-iso usually looks like: ts host unit[pid]: message
    parts = line.split(None, 3)
    if len(parts) >= 4:
        unit = parts[2].split("[", 1)[0].rstrip(":")
        if unit:
            return f"journal:{unit}"
    return "journal:unknown"


def collect_events(
    since: str = "24 hours ago",
    include_journal: bool = True,
    max_lines_per_file: int = 500,
    max_journal_lines: int = 3000,
    max_files: int = 80,
    max_events: int = 10000,
    deadline_at: float | None = None,
) -> list[LogEvent]:
    vocab = load_vocab()
    events = []
    for event in iter_file_events(vocab, max_lines_per_file=max_lines_per_file, max_files=max_files):
        events.append(event)
        if (max_events > 0 and len(events) >= max_events) or (deadline_at and time.monotonic() >= deadline_at):
            break
    if include_journal and (max_events <= 0 or len(events) < max_events) and not (deadline_at and time.monotonic() >= deadline_at):
        for event in iter_journal_events(vocab, since=since, max_lines=max_journal_lines, deadline_at=deadline_at):
            events.append(event)
            if (max_events > 0 and len(events) >= max_events) or (deadline_at and time.monotonic() >= deadline_at):
                break
    if not (deadline_at and time.monotonic() >= deadline_at):
        save_vocab(vocab)
    events.sort(key=lambda item: item.ts)
    return events


def write_events(events: list[LogEvent], path: Path = EVENTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with tmp.open("w") as handle:
            for event in events:
                handle.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract stable keys from Echo logs.")
    parser.add_argument("--since", default="24 hours ago")
    parser.add_argument("--no-journal", action="store_true")
    parser.add_argument("--max-lines-per-file", type=int, default=500)
    parser.add_argument("--max-journal-lines", type=int, default=3000)
    parser.add_argument("--max-files", type=int, default=80)
    parser.add_argument("--max-events", type=int, default=10000)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    events = collect_events(
        since=args.since,
        include_journal=not args.no_journal,
        max_lines_per_file=args.max_lines_per_file,
        max_journal_lines=args.max_journal_lines,
        max_files=args.max_files,
        max_events=args.max_events,
    )
    if args.write:
        write_events(events)
    print(json.dumps({
        "events": len(events),
        "vocab_path": str(VOCAB_PATH),
        "events_path": str(EVENTS_PATH if args.write else ""),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
