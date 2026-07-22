#!/usr/bin/env python3
"""Evidence-based growth queue for Echo."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
QUEUE_PATH = BASE / "memory/growth_queue.json"
OUTCOMES_PATH = BASE / "memory/growth_outcomes.json"
STATE_PATH = BASE / "memory/growth_engine_state.json"
LOG_PATH = BASE / "logs/growth_engine.log"
INCOME_LEDGER_PATH = BASE / "memory/income_dependency_ledger.json"

DOMAIN_WEIGHTS = {
    "reliability": 95,
    "memory": 85,
    "assets": 80,
    "income": 78,
    "autonomy": 72,
    "security": 70,
    "content": 58,
    "maintenance": 55,
}

BLOCKED_TERMS = {
    "reddit credentials",
    "reddit username",
    "reddit password",
    "medium_token",
    "gumroad api key",
    "devto_api_key",
    "api key",
    "tax info",
    "paypal",
    "stripe",
}

HIDDEN_STATUSES = {"done", "rejected", "retired"}


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
    tmp = path.with_name(f"{path.name}.{os_pid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)


def os_pid() -> int:
    import os
    return os.getpid()


def proposal_id(domain: str, title: str) -> str:
    raw = f"{domain}:{title.lower().strip()}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    digest = hashlib.sha1(raw.encode()).hexdigest()[:8]
    return f"growth-{slug}-{digest}"


def classify_domain(text: str) -> str:
    low = text.lower()
    if any(term in low for term in ("failed unit", "stale worker", "venv", "log anomaly", "large logs", "memory text sprawl")):
        return "reliability"
    if any(term in low for term in ("semantic", "memory", "fragmentation", "recall")):
        return "memory"
    if any(term in low for term in ("asset", "tacoma", "workshop", "maintenance", "observation")):
        return "assets"
    if any(term in low for term in ("income", "fiverr", "lead", "affiliate", "dev.to", "medium", "gumroad")):
        return "income"
    if any(term in low for term in ("security", "anomaly", "scope", "log sequence")):
        return "security"
    if any(term in low for term in ("article", "content", "newsletter")):
        return "content"
    return "autonomy"


def is_human_blocked(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in BLOCKED_TERMS)


def score_item(domain: str, evidence_count: int, blocked: bool, source: str) -> int:
    score = DOMAIN_WEIGHTS.get(domain, 50) + min(evidence_count, 5) * 4
    if source == "homeostasis":
        score += 8
    if source == "known_gaps":
        score += 2
    if blocked:
        score -= 40
    return max(1, min(score, 100))


def make_item(title: str, source: str, evidence: list[str]) -> dict:
    domain = classify_domain(" ".join([title, *evidence]))
    blocked = is_human_blocked(" ".join([title, *evidence]))
    score = score_item(domain, len(evidence), blocked, source)
    return {
        "id": proposal_id(domain, title),
        "title": title[:180],
        "domain": domain,
        "source": source,
        "status": "proposed",
        "score": score,
        "blocked_by_human": blocked,
        "risk": "low" if not blocked and domain in {"reliability", "memory", "assets"} else "medium",
        "evidence": evidence[:6],
        "suggested_next_step": suggested_next_step(domain, title, blocked),
        "success_metric": success_metric(domain, title),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


def income_ledger_channels() -> list[dict]:
    data = load_json(INCOME_LEDGER_PATH, {"channels": []})
    channels = data.get("channels", [])
    return channels if isinstance(channels, list) else []


def _income_channel_aliases(channel: dict) -> set[str]:
    aliases = {str(channel.get("channel", "")).lower()}
    label = str(channel.get("label", "")).lower()
    if label:
        aliases.add(label)
    channel_name = str(channel.get("channel", "")).lower()
    if channel_name == "devto":
        aliases.update({"dev.to", "devto"})
    return {alias for alias in aliases if alias}


def _channels_mentioned(text: str, channels: list[dict]) -> list[dict]:
    low = text.lower()
    out = []
    for channel in channels:
        if any(alias in low for alias in _income_channel_aliases(channel)):
            out.append(channel)
    return out


def _looks_like_platform_blocker(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in (
        "need",
        "missing",
        "no ",
        "credential",
        "credentials",
        "api key",
        "activation",
        "captcha",
        "unavailable due to",
        "preventing",
    ))


def rewrite_known_gap_with_income_ledger(title: str, evidence: list[str], channels: list[dict]) -> dict | None:
    text = " ".join([title, *evidence])
    mentioned = _channels_mentioned(text, channels)
    if not mentioned:
        return make_item(title, "known_gaps", evidence)

    actionable = []
    for channel in mentioned:
        status = channel.get("status")
        label = channel.get("label") or channel.get("channel")
        if channel.get("stale_gap") and status == "ready_to_use":
            continue
        if status == "configured_but_captcha":
            actionable.append(make_item(
                f"Resolve captcha routing for {label}",
                "income_dependency_ledger",
                [
                    f"{label}: credentials are configured but captcha blocks automation",
                    *evidence[:2],
                ],
            ))
            continue
        if status == "missing_secret":
            missing = ", ".join(channel.get("missing_keys", []))
            actionable.append(make_item(
                f"Provide missing {label} configuration",
                "income_dependency_ledger",
                [
                    f"{label}: missing required config keys: {missing}",
                    *evidence[:2],
                ],
            ))
            continue
        actionable.append(make_item(
            f"Validate configured {label} income channel",
            "income_dependency_ledger",
            [
                f"{label}: configured but not yet independently validated for income use",
                *evidence[:2],
            ],
        ))

    if not actionable:
        return None
    actionable.sort(key=lambda item: -int(item.get("score", 0)))
    item = actionable[0]
    item["evidence"] = _merge_evidence(item.get("evidence", []), [
        "known_gaps entry was checked against memory/income_dependency_ledger.json",
    ])
    return item


def suggested_next_step(domain: str, title: str, blocked: bool) -> str:
    if blocked:
        return "Ask Andrew for the missing credential/approval before building anything."
    if domain == "reliability":
        return "Create a focused repair or cleanup proposal, then verify it reduces the warning count."
    if domain == "assets":
        return "Connect the observation/task flow for the affected asset and verify a new observation creates useful memory."
    if domain == "memory":
        return "Reduce duplicate/stale memory or add a measured retrieval improvement."
    if domain == "income":
        return "Draft a low-risk income experiment with measurable output before automating outreach."
    if domain == "security":
        return "Keep it defensive and local; add detection/reporting before any active testing capability."
    return "Write a short implementation proposal with measurable acceptance criteria."


def success_metric(domain: str, title: str) -> str:
    if domain == "reliability":
        return "Homeostasis warning count or repeated log anomaly count decreases for 24 hours."
    if domain == "assets":
        return "New observations produce linked asset memory, tasks, or reports without manual repair."
    if domain == "memory":
        return "A later query retrieves the relevant context without duplicate/stale clutter."
    if domain == "income":
        return "Produces a tracked lead, draft, proposal, or revenue-relevant artifact."
    if domain == "security":
        return "Detects or reports a local defensive signal with no out-of-scope network activity."
    return "A concrete artifact is created and independently verified."


def scan_homeostasis() -> list[dict]:
    report = load_json(BASE / "memory/homeostasis_report.json", {})
    items = []
    for finding in report.get("findings", []):
        message = finding.get("message", "")
        if not message:
            continue
        if "recent log anomalies" in message:
            title = "Tune log anomaly signal so recurring self-noise is separated from real anomalies"
        elif "memory text sprawl" in message:
            title = "Reduce memory text sprawl with archive/index rules"
        elif "large logs" in message:
            title = "Review oversized logs and confirm rotation is working"
        elif "venv may need rebuild" in message:
            title = "Resolve Python 3.14 venv drift for stale environments"
        elif "stale worker" in message:
            title = f"Review protected stale worker: {finding.get('worker') or finding.get('unit')}"
        else:
            title = message
        items.append(make_item(title, "homeostasis", [message]))
    return items


def scan_known_gaps() -> list[dict]:
    path = BASE / "memory/known_gaps.md"
    if not path.exists():
        return []
    channels = income_ledger_channels()
    items = []
    for line in path.read_text(errors="replace").splitlines():
        raw = line.strip()
        if not raw.startswith("- "):
            continue
        text = raw[2:].strip()
        if not text or text.startswith("**"):
            continue
        title = re.sub(r"\s+_\(identified.*$", "", text).strip()
        if len(title) < 20:
            continue
        item = rewrite_known_gap_with_income_ledger(title, [text], channels)
        if item:
            items.append(item)
    return items


def scan_standing_tasks() -> list[dict]:
    data = load_json(BASE / "memory/standing_tasks.json", {"tasks": []})
    items = []
    for task in data.get("tasks", [])[:300]:
        text = task.get("task", "")
        if not text or not task.get("self_generated"):
            continue
        weight = float(task.get("weight", 0.5) or 0.5)
        if weight < 0.9:
            continue
        items.append(make_item(text[:180], "standing_tasks", [f"standing task weight={weight}: {text}"]))
    return items


def merge_queue(candidates: list[dict]) -> dict:
    existing = load_json(QUEUE_PATH, {"updated_at": None, "items": []})
    by_id = {item.get("id"): item for item in existing.get("items", []) if item.get("id")}
    now = utcnow()
    retire_stale_income_gap_items(by_id, income_ledger_channels(), now)
    for candidate in candidates:
        prior = by_id.get(candidate["id"])
        if prior:
            if prior.get("status") in {"rejected", "done", "retired"}:
                continue
            prior["score"] = max(int(prior.get("score", 0)), candidate["score"])
            prior["evidence"] = _merge_evidence(prior.get("evidence", []), candidate.get("evidence", []))
            prior["updated_at"] = now
            prior["source"] = prior.get("source") or candidate["source"]
        else:
            by_id[candidate["id"]] = candidate
    items = [item for item in by_id.values() if item.get("status") not in HIDDEN_STATUSES]
    items.sort(key=lambda item: (item.get("blocked_by_human", False), -int(item.get("score", 0)), item.get("created_at", "")))
    return {"updated_at": now, "items": items[:100]}


def retire_stale_income_gap_items(by_id: dict, channels: list[dict], now: str) -> None:
    if not channels:
        return
    for item in by_id.values():
        if item.get("source") != "known_gaps":
            continue
        if item.get("status") not in {"proposed", "ready_for_build", "build_requested"}:
            continue
        text = " ".join([
            str(item.get("title", "")),
            " ".join(str(e) for e in item.get("evidence", [])),
        ])
        if _looks_like_platform_blocker(text) and _channels_mentioned(text, channels):
            item["status"] = "retired"
            item["retired_at"] = now
            item["retired_reason"] = "replaced by income_dependency_ledger platform state"
            item["updated_at"] = now


def _merge_evidence(old: list[str], new: list[str]) -> list[str]:
    out = []
    for item in [*old, *new]:
        if item and item not in out:
            out.append(item)
    return out[:8]


def update_outcomes(queue: dict) -> dict:
    outcomes = load_json(OUTCOMES_PATH, {"updated_at": None, "outcomes": []})
    known = {item.get("proposal_id") for item in outcomes.get("outcomes", [])}
    for item in queue.get("items", []):
        if item.get("status") == "done" and item.get("id") not in known:
            outcomes.setdefault("outcomes", []).append({
                "proposal_id": item["id"],
                "title": item["title"],
                "recorded_at": utcnow(),
                "metric": item.get("success_metric", ""),
                "result": "pending_measurement",
            })
    outcomes["updated_at"] = utcnow()
    outcomes["outcomes"] = outcomes.get("outcomes", [])[-200:]
    return outcomes


def notify_new_top(queue: dict, state: dict, dry_run: bool, notify: bool) -> None:
    if dry_run or not notify:
        return
    top = next((item for item in queue.get("items", []) if not item.get("blocked_by_human")), None)
    if not top or int(top.get("score", 0)) < 85:
        return
    if state.get("last_top_id") == top["id"]:
        return
    try:
        from core.notifier import notify as send_notify

        send_notify(
            "Echo Growth Opportunity",
            f"{top['score']}/100 {top['domain']}: {top['title']}",
            urgent=False,
            phone=True,
        )
        state["last_top_id"] = top["id"]
        state["last_notified_at"] = utcnow()
    except Exception as exc:
        log(f"notify failed: {exc}")


def run(dry_run: bool = False, notify: bool = True) -> dict:
    candidates = []
    candidates.extend(scan_homeostasis())
    candidates.extend(scan_known_gaps())
    candidates.extend(scan_standing_tasks())
    queue = merge_queue(candidates)
    outcomes = update_outcomes(queue)
    state = load_json(STATE_PATH, {})
    notify_new_top(queue, state, dry_run=dry_run, notify=notify)
    if not dry_run:
        write_json(QUEUE_PATH, queue)
        write_json(OUTCOMES_PATH, outcomes)
        write_json(STATE_PATH, state)
    top = queue.get("items", [])[:5]
    log(f"growth_engine candidates={len(candidates)} queue={len(queue.get('items', []))} dry_run={dry_run}")
    return {
        "updated_at": utcnow(),
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "queue_count": len(queue.get("items", [])),
        "top": top,
        "queue_path": str(QUEUE_PATH),
        "outcomes_path": str(OUTCOMES_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, notify=not args.no_notify)
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
