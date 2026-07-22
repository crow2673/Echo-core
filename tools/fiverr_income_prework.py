#!/usr/bin/env python3
"""Create low-risk Fiverr income prework from existing demand leads.

This does not log in, message anyone, or touch browser sessions. It converts
local demand evidence into a small package Andrew/Echo can later use on Fiverr.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEMAND_PATH = BASE / "memory" / "demand_leads.json"
REPORT_DIR = BASE / "memory" / "income_reports"
LATEST_MD = REPORT_DIR / "fiverr_income_prework_latest.md"
LATEST_JSON = REPORT_DIR / "fiverr_income_prework_latest.json"


SERVICE_PATTERNS = [
    {
        "key": "payment_reconciliation",
        "label": "Payment reconciliation automation",
        "keywords": ("stripe", "quickbooks", "reconciliation", "payment", "paypal", "wise", "bookkeeping"),
        "gig_title": "I will build a local payment reconciliation automation script",
        "deliverable": "Python CLI that normalizes CSV exports, flags mismatches, and writes clean accounting-ready files.",
    },
    {
        "key": "intent_monitoring",
        "label": "Intent monitoring pipeline",
        "keywords": ("intent", "keyword alerts", "monitoring pipeline", "qdrant", "vector", "subreddit"),
        "gig_title": "I will build an AI intent monitoring pipeline for Reddit or forums",
        "deliverable": "Local pipeline that ranks posts by buyer intent and exports a reviewable lead list.",
    },
    {
        "key": "sports_data",
        "label": "Sports data scraper/API helper",
        "keywords": ("sports", "wnba", "box scores", "telemetry", "f1", "live sports"),
        "gig_title": "I will build a sports data scraper or analytics helper in Python",
        "deliverable": "Python scraper/API client with retries, normalized output, and a README.",
    },
    {
        "key": "local_ai_tooling",
        "label": "Local AI setup and automation",
        "keywords": ("local ai", "ollama", "self-hosted", "ai agent", "llm", "offline"),
        "gig_title": "I will build a local AI automation tool that runs on your machine",
        "deliverable": "Local Python automation with no hardcoded credentials, config template, and run instructions.",
    },
    {
        "key": "csv_cleanup",
        "label": "CSV cleanup and report automation",
        "keywords": ("csv", "spreadsheet", "export", "data entry", "report", "analytics"),
        "gig_title": "I will automate messy CSV cleanup and reporting with Python",
        "deliverable": "Repeatable script that cleans files, validates columns, and exports reports.",
    },
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_leads() -> list[dict]:
    try:
        data = json.loads(DEMAND_PATH.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def text_for(lead: dict) -> str:
    return " ".join(str(lead.get(k, "")) for k in ("title", "body", "subreddit")).lower()


def score_lead(lead: dict, pattern: dict) -> int:
    text = text_for(lead)
    score = int(lead.get("score") or 0)
    for keyword in pattern["keywords"]:
        if keyword in text:
            score += 5
    if lead.get("subreddit") in {"r/forhire", "r/smallbusiness", "r/automation"}:
        score += 2
    return score


def safe_excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    return compact[:limit].rstrip()


def build_package(limit: int = 5) -> dict:
    leads = load_leads()
    services = []
    used_posts = set()
    for pattern in SERVICE_PATTERNS:
        ranked = sorted(
            leads,
            key=lambda lead: score_lead(lead, pattern),
            reverse=True,
        )
        matches = [
            {
                "title": lead.get("title", ""),
                "subreddit": lead.get("subreddit", ""),
                "url": lead.get("url", ""),
                "score": score_lead(lead, pattern),
                "excerpt": safe_excerpt(lead.get("body", "")),
            }
            for lead in ranked
            if score_lead(lead, pattern) > int(lead.get("score") or 0)
        ][:3]
        if matches:
            used_posts.update(match["url"] for match in matches if match.get("url"))
            services.append({
                "key": pattern["key"],
                "label": pattern["label"],
                "gig_title": pattern["gig_title"],
                "deliverable": pattern["deliverable"],
                "evidence": matches,
                "buyer_message_draft": (
                    f"I can build this as a local Python automation: {pattern['deliverable']} "
                    "I would start with a small sample file/workflow, deliver a tested script, "
                    "and include a README so you can run it without sharing credentials."
                ),
            })

    lead_sources = Counter(str(lead.get("subreddit", "unknown")) for lead in leads)
    return {
        "updated_at": utcnow(),
        "source": str(DEMAND_PATH.relative_to(BASE)),
        "lead_count": len(leads),
        "lead_sources": dict(lead_sources.most_common(10)),
        "service_count": len(services),
        "services": services[:limit],
        "used_post_count": len(used_posts),
        "safety": {
            "browser_login": False,
            "messages_sent": False,
            "credentials_used": False,
            "human_gate": "Andrew still approves any live Fiverr listing, order delivery, or outbound message.",
        },
    }


def render_md(package: dict) -> str:
    lines = [
        "# Fiverr Income Prework",
        "",
        f"Updated: {package['updated_at']}",
        f"Source: `{package['source']}` ({package['lead_count']} local leads)",
        "",
        "No browser login, no messages sent, no credentials used.",
        "",
        "## Best Service Angles",
    ]
    for i, service in enumerate(package["services"], 1):
        lines.extend([
            "",
            f"### {i}. {service['label']}",
            f"- Gig title: {service['gig_title']}",
            f"- Deliverable: {service['deliverable']}",
            f"- Draft buyer response: {service['buyer_message_draft']}",
            "- Evidence:",
        ])
        for match in service["evidence"]:
            lines.append(
                f"  - {match['subreddit']} | score {match['score']} | {match['title']} | {match['url']}"
            )
    lines.extend([
        "",
        "## Human Gate",
        package["safety"]["human_gate"],
        "",
    ])
    return "\n".join(lines)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text)
    tmp.rename(path)


def run(limit: int = 5) -> dict:
    package = build_package(limit=limit)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    md_path = REPORT_DIR / f"fiverr_income_prework_{stamp}.md"
    json_path = REPORT_DIR / f"fiverr_income_prework_{stamp}.json"
    md = render_md(package)
    payload = json.dumps(package, indent=2, sort_keys=True)
    atomic_write(md_path, md)
    atomic_write(json_path, payload)
    atomic_write(LATEST_MD, md)
    atomic_write(LATEST_JSON, payload)
    return {
        "ok": True,
        "md_path": str(md_path.relative_to(BASE)),
        "json_path": str(json_path.relative_to(BASE)),
        "latest_md": str(LATEST_MD.relative_to(BASE)),
        "service_count": package["service_count"],
        "lead_count": package["lead_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    result = run(limit=args.limit)
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
