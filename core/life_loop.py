#!/usr/bin/env python3
"""Echo's evidence-grounded life loop.

This does not claim consciousness. It gives Echo a deterministic cycle:
observe current evidence, choose one grounded priority, record the state, and
leave actionable memory for the next wake cycle.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from core.executive_context import load_context as load_executive_context
from core.executive_context import safe_update as update_executive_context

BASE = Path(__file__).resolve().parents[1]
STATE_PATH = BASE / "memory/life_loop_state.json"
EVENTS_PATH = BASE / "memory/life_loop.jsonl"
LOG_PATH = BASE / "logs/life_loop.log"


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


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _pid() -> int:
    import os

    return os.getpid()


def _top_growth_items(limit: int = 8) -> list[dict]:
    queue = load_json(BASE / "memory/growth_queue.json", {"items": []})
    hidden = {"done", "rejected", "retired"}
    items = [
        item for item in queue.get("items", [])
        if item.get("status") not in hidden and not item.get("blocked_by_human")
    ]
    items.sort(key=lambda item: (-int(item.get("score", 0) or 0), item.get("created_at", "")))
    return items[:limit]


def _open_build_requests(limit: int = 8) -> list[dict]:
    data = load_json(BASE / "memory/growth_build_requests.json", {"requests": []})
    return [
        req for req in data.get("requests", [])
        if req.get("status") in {"requested", "pending_build", "generation_failed"}
    ][:limit]


def _homeostasis() -> dict:
    return load_json(BASE / "memory/homeostasis_report.json", {})


def _income_ledger() -> dict:
    return load_json(BASE / "memory/income_dependency_ledger.json", {"channels": [], "summary": {}})


def _autonomy_model() -> dict:
    model = load_json(BASE / "memory/autonomy_model.json", {})
    try:
        updated = model.get("updated_at")
        if updated:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds()
            if age < 1800:
                return model
        from core.autonomy_model import build_model

        return build_model()
    except Exception:
        return model


def _echo_state() -> dict:
    return load_json(BASE / "memory/echo_state.json", {})


def _self_model() -> dict:
    try:
        from core.self_model import snapshot

        return snapshot()
    except Exception as exc:
        return {
            "identity": "Echo",
            "consciousness": {
                "status": "unknown_not_established",
                "evidence": f"self_model unavailable: {exc}",
            },
        }


def _executive_context() -> dict:
    try:
        context = load_executive_context(create=True)
        return {
            "current_focus": context.get("current_focus"),
            "reason_for_focus": context.get("reason_for_focus") or context.get("focus_reason"),
            "active_task": context.get("active_task"),
            "active_blocker": context.get("active_blocker") or context.get("current_blocker"),
            "risk_level": context.get("risk_level"),
            "system_health": context.get("system_health"),
            "capability_blockers": context.get("capability_blockers", []),
            "maintenance_findings": context.get("maintenance_findings", []),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _normalized_health(value) -> str:
    text = str(value or "unknown").strip().lower()
    if text in {"ok", "okay", "healthy"}:
        return "OK"
    if text in {"warning", "warn", "degraded"}:
        return "warning"
    if text in {"critical", "error", "failed", "fail"}:
        return "critical"
    return str(value or "unknown")


def _has_active_core_operational_incident(homeostasis: dict) -> bool:
    anomaly_summary = homeostasis.get("anomaly_summary", {})
    if int(anomaly_summary.get("active_core_operational_count", 0) or 0) > 0:
        return True
    for item in homeostasis.get("findings", []):
        if item.get("classification") == "core_operational" and item.get("severity") in {"warning", "critical"}:
            return True
        if item.get("severity") == "critical" and item.get("classification") not in {
            "capability_blocker",
            "maintenance",
            "resolved_historical",
        }:
            return True
    return False


def _core_operational_health(evidence: dict) -> str:
    homeostasis = evidence.get("homeostasis", {})
    executive = evidence.get("executive_context", {})
    if _has_active_core_operational_incident(homeostasis):
        report_health = _normalized_health(homeostasis.get("status"))
        return "critical" if report_health == "critical" else "warning"
    executive_health = _normalized_health(executive.get("system_health"))
    if executive_health == "critical":
        return "critical"
    return "OK"


def choose_priority(evidence: dict) -> dict:
    executive = evidence.get("executive_context", {})
    active_blocker = executive.get("active_blocker")
    if active_blocker:
        if isinstance(active_blocker, dict):
            title = active_blocker.get("blocker") or active_blocker.get("summary") or "Executive Context blocker"
        else:
            title = str(active_blocker)
        return {
            "kind": "executive_blocker",
            "title": f"Resolve blocker: {title}",
            "reason": "executive context has an active blocker",
            "next_step": "Resolve the blocker if possible; otherwise report the exact blocker and needed human action.",
            "source": "memory/executive_context.json",
        }

    core_health = _core_operational_health(evidence)
    if core_health not in {"OK", "unknown"}:
        return {
            "kind": "reliability",
            "title": f"Restore system health: {core_health}",
            "reason": "active core operational health incident requires reliability work",
            "next_step": "Prefer health and reliability work before growth or income work.",
            "source": "memory/homeostasis_report.json",
        }

    findings = evidence["homeostasis"].get("findings", [])
    needs = [item for item in findings if item.get("kind") == "needs_andrew"]
    critical_needs = [item for item in needs if item.get("severity") == "critical"]
    if critical_needs:
        first = critical_needs[0]
        return {
            "kind": "needs_andrew",
            "title": first.get("message", "Homeostasis needs Andrew"),
            "reason": "homeostasis has an unresolved critical finding",
            "next_step": "Ask Andrew for the exact missing approval or manual repair.",
            "source": "memory/homeostasis_report.json",
        }

    autonomy_priority = evidence.get("autonomy_model", {}).get("next_priority", {})
    if autonomy_priority.get("kind") == "zero_human_action":
        return {
            "kind": "zero_human_action",
            "title": autonomy_priority.get("title", "Do useful local work before asking Andrew"),
            "reason": autonomy_priority.get("reason", "autonomy model found useful work that does not need Andrew"),
            "next_step": autonomy_priority.get("next_step", "Run a verified local action."),
            "source": autonomy_priority.get("source", "memory/autonomy_model.json"),
        }

    if needs:
        first = needs[0]
        return {
            "kind": "needs_andrew",
            "title": first.get("message", "Homeostasis needs Andrew"),
            "reason": "homeostasis has an unresolved critical or protected finding",
            "next_step": "Ask Andrew for the exact missing approval or manual repair.",
            "source": "memory/homeostasis_report.json",
        }

    income = evidence["income_ledger"]
    missing = [c for c in income.get("channels", []) if c.get("status") == "missing_secret"]
    captcha = [c for c in income.get("channels", []) if c.get("status") == "configured_but_captcha"]
    if missing or captcha:
        channel = missing[0] if missing else captcha[0]
        if channel.get("status") == "missing_secret":
            missing_keys = ", ".join(channel.get("missing_keys", []))
            title = f"Resolve missing income configuration for {channel.get('label')}"
            next_step = f"Ask Andrew only for: {missing_keys}."
        else:
            title = f"Resolve captcha routing for {channel.get('label')}"
            next_step = "Ask Andrew for one routing decision; do not keep retrying automated login."
        return {
            "kind": "income_blocker",
            "title": title,
            "reason": "income ledger contains a real blocker after comparing configured state to stale gaps",
            "next_step": next_step,
            "source": "memory/income_dependency_ledger.json",
        }

    builds = evidence["build_requests"]
    if builds:
        req = builds[0]
        return {
            "kind": "reviewed_build_request",
            "title": req.get("title", "Review queued build request"),
            "reason": "growth bridge promoted this improvement for reviewed implementation",
            "next_step": "Generate or implement the request only under review; do not auto-deploy.",
            "source": "memory/growth_build_requests.json",
        }

    growth = evidence["growth"]
    if growth:
        item = growth[0]
        return {
            "kind": "growth_opportunity",
            "title": item.get("title", "Top growth opportunity"),
            "reason": f"growth score {item.get('score')} from {item.get('source')}",
            "next_step": item.get("suggested_next_step", "Create a measured implementation plan."),
            "source": "memory/growth_queue.json",
        }

    warnings = [item for item in findings if item.get("severity") == "warning"]
    if warnings:
        return {
            "kind": "warning_watch",
            "title": warnings[0].get("message", "Watch current warning"),
            "reason": "homeostasis is warning-only; no immediate action is required",
            "next_step": "Keep monitoring and let growth_engine rank persistent warnings.",
            "source": "memory/homeostasis_report.json",
        }

    return {
        "kind": "steady",
        "title": "Maintain observation and memory",
        "reason": "no critical blocker or high-priority growth item found",
        "next_step": "Continue observing, remembering, and verifying outcomes.",
        "source": "life_loop",
    }


def build_state() -> dict:
    evidence = {
        "observed_at": utcnow(),
        "executive_context": _executive_context(),
        "echo_state": _echo_state(),
        "homeostasis": _homeostasis(),
        "income_ledger": _income_ledger(),
        "autonomy_model": _autonomy_model(),
        "growth": _top_growth_items(),
        "build_requests": _open_build_requests(),
        "self_model": _self_model(),
    }
    priority = choose_priority(evidence)
    consciousness = evidence["self_model"].get("consciousness", {})
    health = _core_operational_health(evidence)
    state = {
        "updated_at": evidence["observed_at"],
        "identity": "Echo operational life loop",
        "consciousness_status": consciousness.get("status", "unknown_not_established"),
        "consciousness_note": consciousness.get(
            "evidence",
            "Subjective experience is not established by available evidence.",
        ),
        "health": health,
        "capabilities_active": [
            "observe",
            "remember",
            "compare",
            "prioritize",
            "request_reviewed_builds",
            "verify_before_claiming_completion",
        ],
        "current_priority": priority,
        "capability_blockers": evidence["homeostasis"].get("capability_blockers", []),
        "maintenance_findings": evidence["homeostasis"].get("maintenance_findings", []),
        "signals": {
            "homeostasis_findings": len(evidence["homeostasis"].get("findings", [])),
            "capability_blockers_seen": len(evidence["homeostasis"].get("capability_blockers", [])),
            "maintenance_findings_seen": len(evidence["homeostasis"].get("maintenance_findings", [])),
            "needs_andrew": len(evidence["homeostasis"].get("needs_andrew", [])),
            "growth_items_seen": len(evidence["growth"]),
            "open_build_requests_seen": len(evidence["build_requests"]),
            "income_summary": evidence["income_ledger"].get("summary", {}),
            "zero_human_actions_seen": len(evidence.get("autonomy_model", {}).get("zero_human_actions", [])),
            "human_gates_seen": len(evidence.get("autonomy_model", {}).get("human_gates", [])),
            "executive_risk_level": evidence["executive_context"].get("risk_level"),
        },
    }
    return state


def sync_priority_to_executive_context(priority: dict, health: str) -> None:
    try:
        update_executive_context(
            {
                "current_focus": priority.get("title"),
                "focus_reason": priority.get("reason"),
                "reason_for_focus": priority.get("reason"),
            },
            source="life_loop",
            reason="life_loop selected current priority",
        )
    except Exception as exc:
        log(f"executive_context update failed: {exc}")


def run(dry_run: bool = False) -> dict:
    state = build_state()
    if not dry_run:
        write_json(STATE_PATH, state)
        append_jsonl(EVENTS_PATH, state)
        sync_priority_to_executive_context(state["current_priority"], state["health"])
        try:
            from core.event_ledger import log_event

            log_event("system", "life_loop", state["current_priority"]["title"], score=1.0)
        except Exception:
            pass
    priority = state["current_priority"]
    log(f"life_loop health={state['health']} priority={priority['kind']}: {priority['title']} dry_run={dry_run}")
    return {
        "dry_run": dry_run,
        "state_path": str(STATE_PATH),
        "events_path": str(EVENTS_PATH),
        "state": state,
    }


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
