#!/usr/bin/env python3
"""Echo autonomy/world-model audit.

This is not an AGI claim. It is a grounding layer for the parts Andrew asked to
build next: reliable autonomy, world model, memory consolidation, reviewed
self-improvement, tool reliability, economic agency, and reasoning depth.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
JSON_PATH = BASE / "memory/autonomy_model.json"
MD_PATH = BASE / "memory/autonomy_model.md"
LOG_PATH = BASE / "logs/autonomy_model.log"

HIDDEN_STATUSES = {"done", "rejected", "retired"}
TEXT_MEMORY_SUFFIXES = {".txt", ".md", ".json"}
LOW_TRUST_NAME_HINTS = ("known_gaps", "last_", "latest_", "current_", "screen_context", "generated")
ARCHIVAL_MEMORY_DIRS = {
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
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with LOG_PATH.open("a") as handle:
        handle.write(line + "\n")
    print(message, flush=True)


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{_pid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)


def _pid() -> int:
    import os

    return os.getpid()


def _age_seconds(path: Path) -> int | None:
    try:
        return int(datetime.now().timestamp() - path.stat().st_mtime)
    except Exception:
        return None


def _memory_inventory() -> dict:
    memory = BASE / "memory"
    files = [p for p in memory.rglob("*") if p.is_file()]
    text_like = [p for p in files if p.suffix.lower() in TEXT_MEMORY_SUFFIXES]
    active_text_like = []
    for path in text_like:
        rel = path.relative_to(memory)
        if rel.parts and rel.parts[0] in ARCHIVAL_MEMORY_DIRS:
            continue
        active_text_like.append(path)
    top_level_text = [p for p in memory.iterdir() if p.is_file() and p.suffix.lower() in TEXT_MEMORY_SUFFIXES]
    stale_hint = [
        str(p.relative_to(BASE))
        for p in top_level_text
        if p.name.startswith(("last_", "latest_", "current_")) or "screen_context" in p.name
    ][:40]

    groups: dict[str, list[str]] = {}
    for path in top_level_text:
        key = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
        key = re.sub(r"^(last|latest|current)_", "", key)
        groups.setdefault(key, []).append(str(path.relative_to(BASE)))
    duplicate_groups = {
        key: vals[:8]
        for key, vals in groups.items()
        if len(vals) > 1
    }

    return {
        "total_files": len(files),
        "text_like_files": len(text_like),
        "active_text_like_files": len(active_text_like),
        "archival_text_like_files": len(text_like) - len(active_text_like),
        "top_level_text_like_files": len(top_level_text),
        "stale_name_hints": stale_hint,
        "duplicate_name_groups": dict(sorted(duplicate_groups.items())[:20]),
        "assessment": "sprawling" if len(active_text_like) > 500 else "manageable",
    }


def _source_trust_model() -> list[dict]:
    sources = [
        ("memory/echo_state.json", "high", "live system snapshot from governor_v2"),
        ("memory/homeostasis_report.json", "high", "current reliability audit"),
        ("memory/interaction_ledger.jsonl", "high", "Andrew/Echo conversation history"),
        ("memory/income_dependency_ledger.json", "medium_high", "credential presence audit; values excluded"),
        ("memory/growth_queue.json", "medium", "ranked proposals; can contain stale evidence until reconciled"),
        ("memory/growth_build_requests.json", "medium", "review queue; safe only after implementation verification"),
        ("memory/outcome_loop_report.json", "high", "verified expected outcomes with observable evidence"),
        ("memory/known_gaps.md", "low", "historically useful but repeatedly stale"),
    ]
    out = []
    for rel, trust, reason in sources:
        path = BASE / rel
        out.append({
            "path": rel,
            "exists": path.exists(),
            "trust": trust if path.exists() else "missing",
            "age_seconds": _age_seconds(path) if path.exists() else None,
            "reason": reason,
        })
    return out


def _growth_items(limit: int = 8) -> list[dict]:
    queue = load_json(BASE / "memory/growth_queue.json", {"items": []})
    items = [
        item for item in queue.get("items", [])
        if item.get("status") not in HIDDEN_STATUSES and not item.get("blocked_by_human")
    ]
    items.sort(key=lambda item: (-int(item.get("score", 0) or 0), item.get("created_at", "")))
    return items[:limit]


def _build_requests(limit: int = 8) -> list[dict]:
    data = load_json(BASE / "memory/growth_build_requests.json", {"requests": []})
    return [
        req for req in data.get("requests", [])
        if req.get("status") in {"requested", "pending_build", "generation_failed"}
    ][:limit]


def _income_channels() -> list[dict]:
    data = load_json(BASE / "memory/income_dependency_ledger.json", {"channels": []})
    channels = data.get("channels", [])
    return channels if isinstance(channels, list) else []


def _homeostasis() -> dict:
    return load_json(BASE / "memory/homeostasis_report.json", {"findings": [], "needs_andrew": []})


def _zero_human_actions(homeostasis: dict, growth: list[dict], builds: list[dict], channels: list[dict], memory: dict) -> list[dict]:
    actions: list[dict] = []

    warning_findings = [
        f for f in homeostasis.get("findings", [])
        if f.get("kind") != "needs_andrew" and f.get("severity") in {"warning", "info"}
    ]
    for finding in warning_findings[:4]:
        actions.append({
            "kind": "reliability_repair",
            "title": finding.get("message", "Review warning"),
            "why_no_human": "local audit/cleanup/reporting work can be done without credentials or approval",
            "next_step": "Create or run a dry-run repair/report and verify the warning count changes.",
            "source": "memory/homeostasis_report.json",
        })

    for req in builds[:4]:
        actions.append({
            "kind": "reviewed_build",
            "title": req.get("title", "Queued reviewed build request"),
            "why_no_human": "request is already constrained to local-only, low-risk, reviewed implementation",
            "next_step": "Implement with dry-run/report first; do not auto-deploy.",
            "source": "memory/growth_build_requests.json",
        })

    ready_income = [c for c in channels if c.get("status") == "ready_to_use"]
    for channel in ready_income[:4]:
        actions.append({
            "kind": "income_prework",
            "title": f"Prepare/use ready income channel: {channel.get('label')}",
            "why_no_human": "configured channel can be researched, drafted, validated, or packaged before any payout gate",
            "next_step": "Produce a tracked draft, lead, validation report, or product package without logging into risky browser flows.",
            "source": "memory/income_dependency_ledger.json",
        })

    for item in growth[:4]:
        actions.append({
            "kind": "growth_proposal",
            "title": item.get("title", "Top growth opportunity"),
            "why_no_human": "proposal is not marked human-blocked",
            "next_step": item.get("suggested_next_step", "Write measurable acceptance criteria."),
            "source": "memory/growth_queue.json",
        })

    if memory.get("assessment") == "sprawling":
        actions.append({
            "kind": "memory_consolidation",
            "title": "Consolidate memory sprawl into indexed trusted summaries",
            "why_no_human": "can run as dry-run/index/report without deleting memories",
            "next_step": "Create archive/index rules for last_/latest_/duplicate text files, then verify retrieval improves.",
            "source": "memory/",
        })

    return actions[:12]


def _human_gates(homeostasis: dict, channels: list[dict]) -> list[dict]:
    gates = []
    for item in homeostasis.get("needs_andrew", []):
        gates.append({
            "kind": "system_review",
            "title": item.get("message", "Needs Andrew review"),
            "reason": "homeostasis classified this as requiring manual review",
            "source": "memory/homeostasis_report.json",
        })
    for channel in channels:
        if channel.get("status") == "missing_secret":
            gates.append({
                "kind": "missing_secret",
                "title": channel.get("label"),
                "reason": "missing required config keys: " + ", ".join(channel.get("missing_keys", [])),
                "source": "memory/income_dependency_ledger.json",
            })
        elif channel.get("status") == "configured_but_captcha":
            gates.append({
                "kind": "captcha_or_platform_gate",
                "title": channel.get("label"),
                "reason": "platform captcha/login wall; do not brute-force or keep retrying",
                "source": "memory/income_dependency_ledger.json",
            })
    return gates


def _outcome_loop_report() -> dict:
    return load_json(BASE / "memory/outcome_loop_report.json", {"summary": {}})


def _maturity_scores(memory: dict, zero_actions: list[dict], human_gates: list[dict], builds: list[dict], channels: list[dict], homeostasis: dict, outcomes: dict) -> dict:
    ready_income = sum(1 for c in channels if c.get("status") == "ready_to_use")
    warnings = len(homeostasis.get("findings", []))
    outcome_summary = outcomes.get("summary", {})
    outcome_total = int(outcome_summary.get("total", 0) or 0)
    outcome_failed = int(outcome_summary.get("failed", 0) or 0)
    outcome_success_rate = outcome_summary.get("success_rate")
    outcome_score = 1
    if outcome_total >= 5:
        outcome_score = 2
    if outcome_total >= 5 and outcome_failed == 0 and outcome_success_rate is not None:
        outcome_score = 3
    return {
        "reliable_autonomy": {
            "score_0_to_5": 2 if human_gates else 3,
            "evidence": f"{len(zero_actions)} no-human actions; {len(human_gates)} human gates",
        },
        "world_model": {
            "score_0_to_5": 2,
            "evidence": "trusted sources are identified, but entity/state/change model is still shallow",
        },
        "memory_consolidation": {
            "score_0_to_5": 1 if memory.get("active_text_like_files", memory.get("text_like_files", 0)) > 500 else 3,
            "evidence": f"{memory.get('active_text_like_files', memory.get('text_like_files'))} active text/json/md files; {len(memory.get('duplicate_name_groups', {}))} duplicate name groups sampled",
        },
        "self_improvement_pipeline": {
            "score_0_to_5": outcome_score,
            "evidence": f"{len(builds)} open reviewed build requests; {outcome_total} tracked outcomes; success_rate={outcome_success_rate}",
        },
        "tool_reliability": {
            "score_0_to_5": 2 if warnings else 3,
            "evidence": f"{warnings} homeostasis findings",
        },
        "economic_agency": {
            "score_0_to_5": 2 if ready_income else 1,
            "evidence": f"{ready_income} ready income channels; platform/payout gates remain",
        },
        "reasoning_depth": {
            "score_0_to_5": 2,
            "evidence": "persistent context and verification exist; local model judgment is still brittle",
        },
    }


def _next_priority(zero_actions: list[dict], human_gates: list[dict]) -> dict:
    if zero_actions:
        action = zero_actions[0]
        return {
            "kind": "zero_human_action",
            "title": action["title"],
            "reason": action["why_no_human"],
            "next_step": action["next_step"],
            "source": action["source"],
        }
    if human_gates:
        gate = human_gates[0]
        return {
            "kind": "human_gate",
            "title": gate["title"],
            "reason": gate["reason"],
            "next_step": "Ask Andrew once, specifically, and do not block unrelated local work.",
            "source": gate["source"],
        }
    return {
        "kind": "steady",
        "title": "Maintain observation and verified growth",
        "reason": "no immediate zero-human action or human gate found",
        "next_step": "Keep observing and closing verified outcomes.",
        "source": "autonomy_model",
    }


def build_model() -> dict:
    homeostasis = _homeostasis()
    growth = _growth_items()
    builds = _build_requests()
    channels = _income_channels()
    memory = _memory_inventory()
    outcomes = _outcome_loop_report()
    zero_actions = _zero_human_actions(homeostasis, growth, builds, channels, memory)
    human_gates = _human_gates(homeostasis, channels)
    scores = _maturity_scores(memory, zero_actions, human_gates, builds, channels, homeostasis, outcomes)
    return {
        "updated_at": utcnow(),
        "scope": [
            "reliable_autonomy",
            "world_model",
            "memory_consolidation",
            "self_improvement_pipeline",
            "tool_reliability",
            "economic_agency",
            "reasoning_depth",
        ],
        "overall_stage": "persistent_specialized_agent",
        "next_priority": _next_priority(zero_actions, human_gates),
        "zero_human_actions": zero_actions,
        "human_gates": human_gates,
        "source_trust_model": _source_trust_model(),
        "memory_inventory": memory,
        "maturity_scores": scores,
        "rule": "Do useful verified local work first; ask Andrew only for true human gates.",
    }


def write_markdown(model: dict) -> None:
    lines = [
        "# Echo Autonomy Model",
        f"_updated {model['updated_at']}_",
        "",
        f"**Stage:** {model['overall_stage']}",
        f"**Rule:** {model['rule']}",
        "",
        "## Next Priority",
        f"- **{model['next_priority']['kind']}**: {model['next_priority']['title']}",
        f"- Next: {model['next_priority']['next_step']}",
        "",
        "## Maturity",
    ]
    for name, info in model["maturity_scores"].items():
        lines.append(f"- {name}: {info['score_0_to_5']}/5 - {info['evidence']}")
    lines += ["", "## Do Without Andrew First"]
    for action in model["zero_human_actions"][:10]:
        lines.append(f"- {action['kind']}: {action['title']} -> {action['next_step']}")
    lines += ["", "## True Human Gates"]
    if model["human_gates"]:
        for gate in model["human_gates"][:10]:
            lines.append(f"- {gate['kind']}: {gate['title']} - {gate['reason']}")
    else:
        lines.append("- none")
    lines += ["", "## Memory Inventory"]
    inv = model["memory_inventory"]
    lines.append(f"- text/json/md files: {inv['text_like_files']}")
    lines.append(f"- active text/json/md files: {inv.get('active_text_like_files', inv['text_like_files'])}")
    lines.append(f"- archival/reference text/json/md files: {inv.get('archival_text_like_files', 0)}")
    lines.append(f"- top-level text/json/md files: {inv['top_level_text_like_files']}")
    lines.append(f"- assessment: {inv['assessment']}")
    MD_PATH.write_text("\n".join(lines) + "\n")


def run(dry_run: bool = False) -> dict:
    model = build_model()
    if not dry_run:
        write_json(JSON_PATH, model)
        write_markdown(model)
    log(f"autonomy_model priority={model['next_priority']['kind']}: {model['next_priority']['title']} dry_run={dry_run}")
    return {"dry_run": dry_run, "json_path": str(JSON_PATH), "md_path": str(MD_PATH), "model": model}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
