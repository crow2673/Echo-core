#!/usr/bin/env python3
"""Safe Echo log maintenance.

Creates a compressed snapshot of oversized append-only logs, then truncates the
live file. Dry-run is the default workflow for review.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
ARCHIVE_DIR = LOG_DIR / "archive"
REPORT_PATH = BASE / "memory/log_maintenance_report.json"
LOG_PATH = LOG_DIR / "log_maintenance.log"

DEFAULT_THRESHOLD_MB = 100
KEEP_TAIL_BYTES = 2 * 1024 * 1024


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with LOG_PATH.open("a") as handle:
        handle.write(line + "\n")
    print(message, flush=True)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{_pid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)


def _pid() -> int:
    import os

    return os.getpid()


def _log_files(threshold_mb: int) -> list[Path]:
    threshold = threshold_mb * 1024 * 1024
    return sorted(
        [
            path for path in LOG_DIR.glob("*.log")
            if path.is_file() and path.stat().st_size >= threshold and path != LOG_PATH
        ],
        key=lambda path: path.stat().st_size,
        reverse=True,
    )


def _tail_bytes(path: Path, limit: int) -> bytes:
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - limit))
        return handle.read()


def archive_and_truncate(path: Path, dry_run: bool) -> dict:
    before = path.stat().st_size
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{path.name}.{stamp}.gz"
    archive_path = ARCHIVE_DIR / archive_name
    tail = b""

    result = {
        "path": str(path.relative_to(BASE)),
        "size_before": before,
        "archive_path": str(archive_path.relative_to(BASE)),
        "tail_preserved_bytes": KEEP_TAIL_BYTES,
        "action": "would_archive_and_truncate" if dry_run else "archived_and_truncated",
    }
    if dry_run:
        return result

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    tail = _tail_bytes(path, KEEP_TAIL_BYTES)
    with path.open("rb") as src, gzip.open(archive_path, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    with path.open("wb") as live:
        if tail:
            live.write(b"[log_maintenance] previous log archived to " + str(archive_path.relative_to(BASE)).encode() + b"\n")
            live.write(tail)
    after = path.stat().st_size
    result["size_after"] = after
    result["archive_size"] = archive_path.stat().st_size
    result["bytes_reclaimed_estimate"] = max(0, before - after)
    return result


def run(dry_run: bool = True, threshold_mb: int = DEFAULT_THRESHOLD_MB) -> dict:
    targets = _log_files(threshold_mb)
    actions = [archive_and_truncate(path, dry_run=dry_run) for path in targets]
    report = {
        "updated_at": utcnow(),
        "dry_run": dry_run,
        "threshold_mb": threshold_mb,
        "target_count": len(targets),
        "actions": actions,
        "total_reclaim_estimate": sum(item.get("bytes_reclaimed_estimate", 0) for item in actions),
    }
    write_json(REPORT_PATH, report)
    log(f"log_maintenance dry_run={dry_run} targets={len(targets)} threshold_mb={threshold_mb}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Archive and truncate oversized logs.")
    parser.add_argument("--threshold-mb", type=int, default=DEFAULT_THRESHOLD_MB)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    report = run(dry_run=not args.apply, threshold_mb=args.threshold_mb)
    if args.print:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
