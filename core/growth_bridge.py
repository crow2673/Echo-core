#!/usr/bin/env python3
"""Promote growth proposals into reviewed build requests."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
QUEUE_PATH = BASE / "memory/growth_queue.json"
REQUESTS_PATH = BASE / "memory/growth_build_requests.json"
STATE_PATH = BASE / "memory/growth_bridge_state.json"
LOG_PATH = BASE / "logs/growth_bridge.log"

MIN_SCORE = 85
ALLOWED_DOMAINS = {"reliability", "memory", "assets", "security"}
ALLOWED_RISKS = {"low"}


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
    except Exception as exc:
        log(f"failed to read {path}: {exc}")
    return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)


def request_id(proposal_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9-]+", "-", proposal_id.lower()).strip("-")
    return f"buildreq-{suffix[:72]}"


def is_eligible(item: dict) -> tuple[bool, str]:
    if item.get("status") not in {"proposed", "ready_for_build"}:
        return False, f"status={item.get('status')}"
    if item.get("blocked_by_human"):
        return False, "blocked_by_human"
    if item.get("domain") not in ALLOWED_DOMAINS:
        return False, f"domain={item.get('domain')}"
    if item.get("risk") not in ALLOWED_RISKS:
        return False, f"risk={item.get('risk')}"
    if int(item.get("score", 0) or 0) < MIN_SCORE:
        return False, f"score={item.get('score')}"
    if item.get("build_request_id"):
        return False, "already_requested"
    return True, "eligible"


def build_description(item: dict) -> str:
    evidence = "; ".join(str(entry) for entry in item.get("evidence", [])[:4])
    title = item.get("title", "Echo improvement")
    metric = item.get("success_metric", "A concrete improvement is verified.")
    return (
        f"Build a reviewed Echo improvement for: {title}. "
        f"Goal: {metric} "
        f"Reach: Andrew/Echo reliability and local autonomy. "
        f"Evidence: {evidence}. "
        "Constraints: keep it local-only, low-risk, non-destructive, no credential changes, "
        "no external purchases, no unattended deployment, and write a dry-run/report path before "
        "any repair action."
    )


def load_requests() -> dict:
    return load_json(REQUESTS_PATH, {"updated_at": None, "requests": []})


def already_requested(requests: dict, proposal_id: str) -> bool:
    return any(req.get("proposal_id") == proposal_id for req in requests.get("requests", []))


def promote_one(queue: dict, requests: dict, generate: bool) -> tuple[dict | None, str]:
    for item in queue.get("items", []):
        ok, reason = is_eligible(item)
        if not ok:
            continue
        proposal_id = item.get("id")
        if not proposal_id:
            continue
        if already_requested(requests, proposal_id):
            item["status"] = "build_requested"
            item["build_request_id"] = request_id(proposal_id)
            return None, "top eligible proposal already has a request"

        req = {
            "request_id": request_id(proposal_id),
            "proposal_id": proposal_id,
            "title": item.get("title"),
            "domain": item.get("domain"),
            "score": item.get("score"),
            "risk": item.get("risk"),
            "status": "requested",
            "created_at": utcnow(),
            "updated_at": utcnow(),
            "build_description": build_description(item),
            "evidence": item.get("evidence", [])[:6],
            "success_metric": item.get("success_metric", ""),
            "generated_build": None,
        }
        if generate:
            from core.self_build import generate as generate_build

            build = generate_build(req["build_description"])
            req["generated_build"] = build
            req["status"] = "pending_build" if build.get("status") == "pending" else "generation_failed"
            item["status"] = req["status"]
            item["generated_build_name"] = build.get("name")
        else:
            item["status"] = "build_requested"
        item["build_request_id"] = req["request_id"]
        item["updated_at"] = utcnow()
        requests.setdefault("requests", []).append(req)
        return req, "promoted"
    return None, "no eligible proposal"


def notify_request(req: dict, dry_run: bool, notify: bool) -> None:
    if dry_run or not notify or not req:
        return
    try:
        from core.notifier import notify as send_notify

        send_notify(
            "Echo Growth Build Request",
            f"{req.get('score')}/100 {req.get('domain')}: {req.get('title')}",
            urgent=False,
            phone=True,
        )
    except Exception as exc:
        log(f"notify failed: {exc}")


def run(dry_run: bool = False, notify: bool = True, generate: bool = False) -> dict:
    queue = load_json(QUEUE_PATH, {"updated_at": None, "items": []})
    requests = load_requests()
    state = load_json(STATE_PATH, {})

    req, reason = promote_one(queue, requests, generate=generate)
    now = utcnow()
    requests["updated_at"] = now
    requests["requests"] = requests.get("requests", [])[-200:]
    state.update({
        "updated_at": now,
        "last_reason": reason,
        "last_request_id": req.get("request_id") if req else state.get("last_request_id"),
    })

    if not dry_run:
        write_json(QUEUE_PATH, queue)
        write_json(REQUESTS_PATH, requests)
        write_json(STATE_PATH, state)
    notify_request(req, dry_run=dry_run, notify=notify)
    log(f"growth_bridge reason={reason} generated={bool(generate)} dry_run={dry_run}")
    return {
        "updated_at": now,
        "dry_run": dry_run,
        "generated": bool(generate),
        "reason": reason,
        "request": req,
        "requests_path": str(REQUESTS_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--generate", action="store_true", help="Generate a pending self_build artifact for review.")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, notify=not args.no_notify, generate=args.generate)
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
