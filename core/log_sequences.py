#!/usr/bin/env python3
"""Build per-source log-key sequences for Echo log anomaly detection."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.log_keys import VOCAB_PATH, LogEvent, collect_events, load_vocab, write_events

BASE = Path(__file__).resolve().parents[1]
MEMORY_DIR = BASE / "memory"
SEQUENCES_PATH = MEMORY_DIR / "log_key_sequences.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_index() -> dict[str, int]:
    vocab = load_vocab(VOCAB_PATH)
    out = {}
    for key, item in vocab.get("templates", {}).items():
        try:
            out[key] = int(item["index"])
        except Exception:
            continue
    return out


def build_sequences(
    events: list[LogEvent],
    seqlen: int = 10,
    min_source_events: int = 12,
    max_sequences: int = 20000,
    deadline_at: float | None = None,
) -> dict:
    """Return model-ready rolling sequences grouped by source."""
    key_to_index = _key_index()
    grouped: dict[str, list[LogEvent]] = defaultdict(list)
    for event in events:
        grouped[event.source].append(event)

    sequences = []
    sequence_limit_reached = False
    deadline_reached = False
    sorted_groups = sorted(
        grouped.items(),
        key=lambda item: max((event.ts for event in item[1]), default=""),
        reverse=True,
    )
    for source, source_events in sorted_groups:
        if deadline_at and time.monotonic() >= deadline_at:
            deadline_reached = True
            break
        source_events.sort(key=lambda item: item.ts)
        if len(source_events) < min_source_events:
            continue
        indices = [key_to_index[event.key] for event in source_events]
        for end in range(len(indices) - 1, seqlen - 1, -1):
            if deadline_at and time.monotonic() >= deadline_at:
                deadline_reached = True
                break
            window = indices[end - seqlen:end]
            target = indices[end]
            event = source_events[end]
            sequences.append({
                "source": source,
                "ts": event.ts,
                "input": window,
                "target": target,
                "target_key": event.key,
                "raw_hash": event.raw_hash,
            })
            if max_sequences > 0 and len(sequences) >= max_sequences:
                sequence_limit_reached = True
                break
        if sequence_limit_reached or deadline_reached:
            break
    sequences.sort(key=lambda item: item.get("ts", ""))

    return {
        "version": 1,
        "created_at": _utc_now(),
        "seqlen": seqlen,
        "event_count": len(events),
        "source_count": len(grouped),
        "key_to_index": key_to_index,
        "index_to_key": {str(v): k for k, v in key_to_index.items()},
        "sequences": sequences,
        "bounds": {
            "max_sequences": max_sequences,
            "sequence_limit_reached": sequence_limit_reached,
            "deadline_reached": deadline_reached,
        },
    }


def save_sequences(payload: dict, path: Path = SEQUENCES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def build_from_logs(
    since: str = "24 hours ago",
    include_journal: bool = True,
    seqlen: int = 10,
    max_lines_per_file: int = 500,
    max_journal_lines: int = 3000,
    max_files: int = 80,
    max_events: int = 10000,
    max_sequences: int = 20000,
    deadline_at: float | None = None,
) -> dict:
    events = collect_events(
        since=since,
        include_journal=include_journal,
        max_lines_per_file=max_lines_per_file,
        max_journal_lines=max_journal_lines,
        max_files=max_files,
        max_events=max_events,
        deadline_at=deadline_at,
    )
    write_events(events)
    return build_sequences(events, seqlen=seqlen, max_sequences=max_sequences, deadline_at=deadline_at)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Echo log-key sequences.")
    parser.add_argument("--since", default="24 hours ago")
    parser.add_argument("--no-journal", action="store_true")
    parser.add_argument("--seqlen", type=int, default=10)
    parser.add_argument("--max-lines-per-file", type=int, default=500)
    parser.add_argument("--max-journal-lines", type=int, default=3000)
    parser.add_argument("--max-files", type=int, default=80)
    parser.add_argument("--max-events", type=int, default=10000)
    parser.add_argument("--max-sequences", type=int, default=20000)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    payload = build_from_logs(
        since=args.since,
        include_journal=not args.no_journal,
        seqlen=args.seqlen,
        max_lines_per_file=args.max_lines_per_file,
        max_journal_lines=args.max_journal_lines,
        max_files=args.max_files,
        max_events=args.max_events,
        max_sequences=args.max_sequences,
    )
    if args.write:
        save_sequences(payload)
    print(json.dumps({
        "events": payload["event_count"],
        "sources": payload["source_count"],
        "keys": len(payload["key_to_index"]),
        "sequences": len(payload["sequences"]),
        "sequences_path": str(SEQUENCES_PATH if args.write else ""),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
