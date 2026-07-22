#!/usr/bin/env python3
"""Report active vs archival Echo memory.

This does not delete or move files. It defines the boundary between working
memory and archival/reference stores, then writes an index Echo can use for
future consolidation work.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MEMORY = BASE / "memory"
REPORT = MEMORY / "memory_consolidation_report.json"
MD_REPORT = MEMORY / "memory_consolidation_report.md"
LOG = BASE / "logs/memory_consolidation.log"

TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl"}
ARCHIVAL_DIRS = {
    "archive_consolidated",
    "obsidian_vault",
    "opportunities",
    "finetune_data",
    "exported_models",
    "lora_adapters",
    "ollama",
    "articles",
    "blog",
    "weekly_reports",
    "income_reports",
    "product_pages",
    "newsletter_drafts",
    "outreach_drafts",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with LOG.open("a") as handle:
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


def is_archival(path: Path) -> bool:
    try:
        rel = path.relative_to(MEMORY)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] in ARCHIVAL_DIRS)


def build_report() -> dict:
    files = [p for p in MEMORY.rglob("*") if p.is_file()]
    text_files = [p for p in files if p.suffix.lower() in TEXT_SUFFIXES]
    active_text = [p for p in text_files if not is_archival(p)]
    archival_text = [p for p in text_files if is_archival(p)]

    by_top_dir = Counter()
    active_top = []
    for path in active_text:
        rel = path.relative_to(MEMORY)
        top = rel.parts[0] if len(rel.parts) > 1 else "."
        by_top_dir[top] += 1
        if len(active_top) < 80:
            active_top.append(str(path.relative_to(BASE)))

    stale_name_hints = [
        str(p.relative_to(BASE))
        for p in active_text
        if p.name.startswith(("last_", "latest_", "current_")) or "screen_context" in p.name
    ][:80]

    report = {
        "updated_at": utcnow(),
        "archival_dirs": sorted(ARCHIVAL_DIRS),
        "total_text_files": len(text_files),
        "active_text_files": len(active_text),
        "archival_text_files": len(archival_text),
        "active_by_top_dir": dict(sorted(by_top_dir.items(), key=lambda item: (-item[1], item[0]))),
        "active_samples": active_top,
        "stale_name_hints": stale_name_hints,
        "next_safe_steps": [
            "Treat archival_dirs as reference memory, not active working memory.",
            "Create canonical summaries for duplicate top-level last_/latest_/current_ files.",
            "Only move or delete files after a separate reviewed plan identifies their consumers.",
        ],
    }
    return report


def write_markdown(report: dict) -> None:
    lines = [
        "# Echo Memory Consolidation Report",
        f"_updated {report['updated_at']}_",
        "",
        f"- total text/json/md/jsonl files: {report['total_text_files']}",
        f"- active working-memory text files: {report['active_text_files']}",
        f"- archival/reference text files: {report['archival_text_files']}",
        "",
        "## Active By Top Directory",
    ]
    for name, count in list(report["active_by_top_dir"].items())[:40]:
        lines.append(f"- {name}: {count}")
    lines += ["", "## Stale Name Hints"]
    for path in report["stale_name_hints"][:40]:
        lines.append(f"- {path}")
    lines += ["", "## Next Safe Steps"]
    for step in report["next_safe_steps"]:
        lines.append(f"- {step}")
    MD_REPORT.write_text("\n".join(lines) + "\n")


def run(print_report: bool = False) -> dict:
    report = build_report()
    write_json(REPORT, report)
    write_markdown(report)
    log(f"memory_consolidation active={report['active_text_files']} archival={report['archival_text_files']}")
    if print_report:
        print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    run(print_report=args.print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
