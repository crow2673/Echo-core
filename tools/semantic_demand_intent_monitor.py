#!/usr/bin/env python3
"""Offline semantic demand and intent monitor prototype.

This prototype reads existing demand leads, classifies intent with deterministic
rules, clusters likely duplicates, and writes ranked local reports. It does not
scrape, contact users, create growth requests, or update Executive Context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
LEADS_PATH = BASE / "memory" / "demand_leads.json"
CANDIDATES_PATH = BASE / "memory" / "demand_intent_candidates.json"
REPORT_PATH = BASE / "memory" / "demand_intent_report.json"

DEFAULT_LIMIT = 250
DEFAULT_DAYS = 90
MAX_EVIDENCE_CHARS = 280

INTENT_CLASSES = {
    "genuine_problem_need",
    "casual_discussion",
    "advice_request",
    "complaint",
    "buyer_intent",
    "job_opportunity",
    "spam_promotion",
    "duplicate_reposted_demand",
    "stale_lead",
    "unclear_intent",
}

PRIMARY_LABELS = {
    "direct_buyer_request",
    "hiring_request",
    "partnership_request",
    "advice_request",
    "research_about_demand",
    "tutorial_or_showcase",
    "self_promotion",
    "general_discussion",
    "spam_or_low_signal",
    "unclear",
}

CAPABILITY_STATES = {
    "ready_now",
    "mostly_ready",
    "partial",
    "major_gap",
    "incompatible_or_unsafe",
    "unclear",
}

STATE_SCORES = {
    "ready_now": 0.92,
    "mostly_ready": 0.76,
    "partial": 0.52,
    "major_gap": 0.24,
    "incompatible_or_unsafe": 0.05,
    "unclear": 0.34,
}

BASE_MODULES = {
    "demand_intent_monitoring": [
        "tools/demand_scanner.py",
        "tools/semantic_demand_intent_monitor.py",
        "core/initiative_engine.py",
        "core/notifier.py",
        "core/semantic_memory.py",
    ],
    "workflow_automation": [
        "core/code_sandbox.py",
        "core/self_build.py",
        "tools/opportunity_hunter.py",
        "tools/fiverr_income_prework.py",
    ],
    "data_reporting": [
        "assets/report_generator.py",
        "tools/fiverr_income_prework.py",
        "core/code_sandbox.py",
    ],
    "local_ai_tooling": [
        "core/income_scanner.py",
        "core/code_sandbox.py",
        "tools/ollama_watchdog.py",
    ],
    "content_publishing": [
        "core/content_pipeline.py",
        "tools/newsletter_composer.py",
        "tools/fiverr_income_prework.py",
    ],
    "system_reliability": [
        "tools/operational_audit.py",
        "tools/semantic_demand_intent_monitor.py",
        "core/notifier.py",
    ],
}

CAPABILITY_PATTERNS = {
    "demand_intent_monitoring": (
        "reddit", "leads", "intent", "monitor", "monitoring", "alert",
        "keyword", "signals", "opportunity", "qdrant", "embedding", "vector",
    ),
    "workflow_automation": (
        "automate", "automation", "workflow", "script", "bot", "api",
        "integrate", "webhook", "zapier", "n8n", "airtable", "notion",
        "manual", "tedious", "save time",
    ),
    "data_reporting": (
        "csv", "spreadsheet", "sheet", "dashboard", "report", "analytics",
        "reconciliation", "quickbooks", "stripe", "paypal", "metrics",
    ),
    "local_ai_tooling": (
        "local ai", "ollama", "llm", "agent", "agents", "rag", "openai",
        "gpt", "claude", "qwen", "prompt",
    ),
    "content_publishing": (
        "article", "newsletter", "blog", "dev.to", "medium", "seo",
        "youtube", "content", "publish",
    ),
    "system_reliability": (
        "logs", "backup", "uptime", "health", "server", "linux",
        "homelab", "monitoring", "daemon",
    ),
}

BUYER_PATTERNS = (
    "need someone", "need help", "looking for someone", "can someone",
    "anyone able", "willing to pay", "quote",
    "build for me", "hire", "hiring a",
)
JOB_PATTERNS = ("[hiring]", "hiring", "remote", "salary", "per month", "contract", "full-time", "backend developer")
PARTNERSHIP_PATTERNS = ("sales partner", "design partner", "co-founder", "cofounder", "commission", "revenue share", "bring us leads")
CONTACT_PATTERNS = ("dm me", "send me", "apply", "email me", "message me", "contact", "please send", "fill out", "interested")
FIRST_PERSON_NEED_PATTERNS = (
    "i need", "we need", "i'm looking for", "im looking for", "we're looking for",
    "we are looking for", "i am looking for", "looking for someone", "need someone",
    "i looking for", "looking for a solid team", "looking for a team",
    "need help", "i'm trying to build", "we're trying to build", "i want someone",
    "[needed]",
)
DIRECT_WORK_PATTERNS = (
    "build", "automate", "set up", "create", "develop", "fix", "scrape",
    "integrate", "workflow", "script", "dashboard", "prototype", "tool",
)
PROBLEM_PATTERNS = ("problem", "struggling", "manual", "tedious", "wasting", "pain", "can't", "cannot", "failed", "issue")
ADVICE_PATTERNS = (
    "how do i", "how are people", "how would you", "what options",
    "any advice", "need advice", "looking for advice", "recommend",
    "should i", "best way",
)
COMPLAINT_PATTERNS = ("hate", "frustrated", "annoying", "broken", "doesn't work", "not working", "terrible")
PROMO_PATTERNS = (
    "i built", "i made", "we built", "launched", "launching", "check out",
    "my app", "my tool", "my service", "available for hire", "[for hire]",
    "portfolio", "beta testers", "looking for feedback", "need feedback",
    "looking for testers", "looking for honest feedback", "shipped v",
    "shipped v1", "i made $", "turned it into a saas", "willing to test",
    "looking for a few businesses", "looking for a small number",
)
SPAM_PATTERNS = ("survey", "get paid", "onlyfans", "casino", "crypto giveaway", "airdrop")
URGENT_PATTERNS = ("asap", "urgent", "today", "immediately", "deadline", "this week", "by tomorrow", "blocked")
RESEARCH_PATTERNS = (
    "i scraped", "we scraped", "i analyzed", "analysis", "research", "report",
    "what people actually want", "what users want", "market", "validated market",
    "case study", "what i found", "exact process",
)
TUTORIAL_PATTERNS = (
    "how i", "here is how", "here's how", "tutorial", "guide", "walkthrough",
    "working model", "what worked", "what broke", "lessons learned",
    "here is a", "here is the", "the stack",
)
AGENCY_PROMO_PATTERNS = (
    "we build", "our agency", "my agency", "we handle", "our job", "our service",
    "we offer", "looking for clients", "bring us leads", "we're expanding",
)
QUOTE_OR_REPOST_PATTERNS = (
    "people ask", "users ask", "comments said", "reddit comments", "i keep seeing",
    "same story", "example from", "real example", "what people are asking",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def load_leads(path: Path = LEADS_PATH) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.rename(path)


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def lead_id(lead: dict[str, Any]) -> str:
    raw = str(lead.get("post_id") or lead.get("url") or lead.get("title") or "")
    if raw:
        return raw[:80]
    digest = hashlib.sha1(json.dumps(lead, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"lead-{digest}"


def lead_text(lead: dict[str, Any]) -> str:
    return " ".join(str(lead.get(key, "") or "") for key in ("title", "body", "subreddit"))


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(term_in_text(text, pattern) for pattern in patterns)


def matches(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if term_in_text(text, pattern)]


def term_in_text(text: str, term: str) -> bool:
    normalized = norm_text(term)
    if not normalized:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None


def problem_summary(lead: dict[str, Any]) -> str:
    title = re.sub(r"\s+", " ", str(lead.get("title", "") or "")).strip()
    body = re.sub(r"\s+", " ", str(lead.get("body", "") or "")).strip()
    if body and len(title) < 35:
        return f"{title}: {body[:160]}".strip(": ")
    return title[:200] or body[:200] or "No usable problem summary"


def capability_match(text: str) -> tuple[str, float, list[str]]:
    hits: list[tuple[str, int, list[str]]] = []
    for capability, keywords in CAPABILITY_PATTERNS.items():
        found = [keyword for keyword in keywords if term_in_text(text, keyword)]
        if found:
            hits.append((capability, len(found), found[:6]))
    if not hits:
        return "missing_capability", 0.15, []
    hits.sort(key=lambda item: item[1], reverse=True)
    capability, count, evidence = hits[0]
    score = min(1.0, 0.35 + count * 0.12)
    return capability, round(score, 3), evidence


def ambiguity_features(text: str, title: str, subreddit: str) -> dict[str, Any]:
    first_person_need = matches(text, FIRST_PERSON_NEED_PATTERNS)
    direct_work = matches(text, DIRECT_WORK_PATTERNS)
    explicit_payment = []
    if re.search(r"\b(budget|fixed budget|pay|paid|payment|compensation|rate|salary|commission)\b", text):
        explicit_payment.append("payment language")
    if re.search(r"(\$\s?\d+|\d+\s?(usd|eur|gbp)|\d+\s?/\s?hour|per hour|per month)", text):
        explicit_payment.append("amount/rate")

    features = {
        "requester_vs_provider_orientation": "unclear",
        "first_person_need_language": first_person_need,
        "direct_work_language": direct_work,
        "explicit_hiring_payment_budget_language": sorted(set(matches(text, JOB_PATTERNS) + explicit_payment)),
        "call_to_action_contact_intent": matches(text, CONTACT_PATTERNS),
        "research_report_showcase_language": matches(text, RESEARCH_PATTERNS),
        "tutorial_helpful_content_language": matches(text, TUTORIAL_PATTERNS),
        "agency_self_promotion_language": matches(text, AGENCY_PROMO_PATTERNS),
        "provider_offer_language": matches(text, PROMO_PATTERNS),
        "quoted_or_reposted_demand_language": matches(text, QUOTE_OR_REPOST_PATTERNS),
        "question_language": bool("?" in title or matches(text, ADVICE_PATTERNS)),
        "offer_distinction": "unknown",
    }

    provider_strength = sum(bool(features[key]) for key in (
        "research_report_showcase_language",
        "tutorial_helpful_content_language",
        "agency_self_promotion_language",
        "provider_offer_language",
    ))
    requester_strength = sum(bool(features[key]) for key in (
        "first_person_need_language",
        "direct_work_language",
        "explicit_hiring_payment_budget_language",
        "call_to_action_contact_intent",
    ))

    if features["agency_self_promotion_language"]:
        features["requester_vs_provider_orientation"] = "provider"
    elif "forhire" in subreddit or "[hiring]" in title or title.startswith("hiring "):
        features["requester_vs_provider_orientation"] = "requester"
    elif provider_strength >= 2 and requester_strength < 3:
        features["requester_vs_provider_orientation"] = "provider"
    elif features["research_report_showcase_language"] or features["quoted_or_reposted_demand_language"]:
        features["requester_vs_provider_orientation"] = "reporter"
    elif features["first_person_need_language"] and features["direct_work_language"]:
        features["requester_vs_provider_orientation"] = "requester"
    elif requester_strength >= 3:
        features["requester_vs_provider_orientation"] = "requester"
    elif requester_strength and provider_strength:
        features["requester_vs_provider_orientation"] = "mixed"

    if features["requester_vs_provider_orientation"] == "requester":
        features["offer_distinction"] = "asks_for_work_or_help"
    elif features["requester_vs_provider_orientation"] == "provider":
        features["offer_distinction"] = "offers_or_showcases_service"
    elif features["requester_vs_provider_orientation"] == "reporter":
        features["offer_distinction"] = "reports_on_demand_or_teaches"

    return features


def primary_label_for(intent: str, features: dict[str, Any], text: str, subreddit: str) -> str:
    orientation = features.get("requester_vs_provider_orientation")
    has_payment = bool(features.get("explicit_hiring_payment_budget_language"))
    has_contact = bool(features.get("call_to_action_contact_intent"))
    has_direct_work = bool(features.get("direct_work_language"))
    has_need = bool(features.get("first_person_need_language"))
    strong_direct = (
        has_need
        and has_direct_work
        and (
            "need someone" in text
            or "need help" in text
            or "looking for someone" in text
            or "looking for a solid team" in text
            or "[needed]" in text
            or "i looking for" in text
            or has_payment
            or has_contact
        )
    )

    if matches(text, SPAM_PATTERNS):
        return "spam_or_low_signal"
    if features.get("agency_self_promotion_language") and not (has_need and has_direct_work):
        return "self_promotion"
    if features.get("research_report_showcase_language") or features.get("quoted_or_reposted_demand_language"):
        return "research_about_demand"
    if features.get("provider_offer_language") and not strong_direct:
        return "tutorial_or_showcase"
    if features.get("tutorial_helpful_content_language"):
        return "tutorial_or_showcase"
    if features.get("provider_offer_language") and orientation in {"provider", "mixed"} and not has_contact:
        return "tutorial_or_showcase"
    if intent == "job_opportunity" or "[hiring]" in text or "forhire" in subreddit:
        if matches(text, PARTNERSHIP_PATTERNS):
            return "partnership_request"
        return "hiring_request"
    if matches(text, PARTNERSHIP_PATTERNS):
        return "partnership_request"
    if intent == "advice_request" and not strong_direct:
        return "advice_request"
    if strong_direct:
        return "direct_buyer_request"
    if intent == "advice_request":
        return "advice_request"
    if intent in {"casual_discussion", "complaint", "genuine_problem_need"}:
        return "general_discussion"
    return "unclear"


def score_adjustments_for(label: str, features: dict[str, Any]) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []

    def add(rule: str, delta: float, reason: str) -> None:
        adjustments.append({"rule": rule, "delta": delta, "reason": reason})

    if label == "direct_buyer_request":
        add("direct_request_bonus", 0.10, "first-person request plus specific work evidence")
    elif label == "hiring_request":
        add("hiring_separate_label", -0.04, "valuable but not direct project-buyer demand")
    elif label == "partnership_request":
        add("partnership_penalty", -0.12, "partnership/commission request is not direct buyer demand")
    elif label == "advice_request":
        add("advice_penalty", -0.16, "asks for recommendations rather than asking Echo to perform work")
    elif label == "research_about_demand":
        add("research_penalty", -0.26, "reports on demand rather than requesting work")
    elif label == "tutorial_or_showcase":
        add("showcase_penalty", -0.28, "showcases or teaches an existing build")
    elif label == "self_promotion":
        add("provider_penalty", -0.32, "author is offering/promoting a service")
    elif label == "general_discussion":
        add("discussion_penalty", -0.18, "discussion/problem signal without direct work request")
    elif label == "spam_or_low_signal":
        add("low_signal_penalty", -0.40, "spam or low-quality paid task pattern")
    elif label == "unclear":
        add("unclear_penalty", -0.22, "insufficient evidence to infer intent")

    if features.get("quoted_or_reposted_demand_language"):
        add("quoted_demand_penalty", -0.08, "demand language appears reported or quoted, not necessarily requested by author")
    if features.get("agency_self_promotion_language"):
        add("agency_promotion_penalty", -0.10, "agency/service-provider language present")
    if features.get("explicit_hiring_payment_budget_language") and label in {"direct_buyer_request", "hiring_request"}:
        add("payment_evidence_bonus", 0.04, "payment, budget, hiring, or rate evidence present")

    return adjustments


def apply_score_correction(base_score: float, adjustments: list[dict[str, Any]]) -> float:
    corrected = base_score + sum(float(item.get("delta", 0.0)) for item in adjustments)
    return round(max(0.0, min(1.0, corrected)), 4)


def platform_hits(text: str) -> list[str]:
    platforms = (
        "gohighlevel", "n8n", "zapier", "make", "airtable", "notion",
        "google sheets", "gmail", "quickbooks", "stripe", "paypal",
        "whatsapp", "reddit", "claude", "openai", "qdrant", "upwork",
        "emulator", "pubg", "ios", "android", "instagram", "facebook",
    )
    return [platform for platform in platforms if term_in_text(text, platform)]


def requested_deliverable(text: str, title: str) -> str:
    if any(term_in_text(text, term) for term in ("video workflow", "ai video", "video editing", "video", "ai avatars")):
        return "ai_video_workflow"
    if any(term_in_text(text, term) for term in ("appointment setter", "appointment setters", "cold caller", "cold callers", "sales partner")):
        return "human_sales_or_appointment_setting"
    if any(term_in_text(text, term) for term in ("game automation", "emulator", "pubg")):
        return "game_or_emulator_automation"
    if any(term_in_text(text, term) for term in ("copywriter", "ghostwriter", "co writer", "content")):
        return "content_writing_or_marketing"
    if term_in_text(text, "gohighlevel"):
        return "gohighlevel_operations_automation"
    if any(term_in_text(text, term) for term in ("csv", "spreadsheet", "data scraping", "scraping", "reconciliation")):
        return "data_cleanup_scraping_or_reporting"
    if any(term_in_text(text, term) for term in ("n8n", "zapier", "make", "workflow")):
        return "workflow_or_webhook_automation"
    if any(term_in_text(text, term) for term in ("intent monitoring", "reddit monitoring", "lead signals", "monitor reddit", "monitor leads")):
        return "demand_or_intent_monitoring"
    if any(term_in_text(text, term) for term in ("app development", "prototype", "backend", "full stack", "mobile app")):
        return "custom_app_or_backend_development"
    if any(term_in_text(text, term) for term in ("qa automation", "software tester", "test framework")):
        return "qa_automation"
    if any(term_in_text(text, term) for term in ("landing page", "website", "seo")):
        return "website_or_landing_page"
    return title[:80] or "unclear_deliverable"


def capability_fit_for(
    text: str,
    title: str,
    primary_label: str,
    capability: str,
    features: dict[str, Any],
) -> dict[str, Any]:
    deliverable = requested_deliverable(text, title)
    platforms = platform_hits(text)
    modules = list(BASE_MODULES.get(capability, []))
    missing: list[str] = []
    external: list[str] = []
    human_setup: list[str] = []
    skills: list[str] = []
    adjustments: list[dict[str, Any]] = []
    state = "unclear"
    risk = "medium"
    estimated_new_code = "unknown"
    time_to_prototype = "unknown"
    work_type = "unclear"
    deployment = "unknown"

    def add_adjust(rule: str, delta: float, reason: str) -> None:
        adjustments.append({"rule": rule, "delta": delta, "reason": reason})

    if capability in BASE_MODULES:
        add_adjust("existing_module_match", 0.08, f"Echo has reusable modules for {capability}")

    if any(term_in_text(text, term) for term in ("csv", "spreadsheet", "script", "report", "scraping", "reconciliation")):
        skills.extend(["python scripting", "data parsing", "report generation"])
    if any(term_in_text(text, term) for term in ("api", "webhook", "workflow", "n8n", "zapier", "make", "gohighlevel")):
        skills.extend(["API/webhook integration", "workflow automation design"])
    if any(term_in_text(text, term) for term in ("llm", "ai", "agent", "claude", "openai")):
        skills.extend(["local/hosted AI workflow design", "prompt/tool orchestration"])
    if any(term_in_text(text, term) for term in ("dashboard", "website", "landing page", "frontend")):
        skills.extend(["web UI generation", "frontend implementation"])

    if deliverable in {"data_cleanup_scraping_or_reporting", "demand_or_intent_monitoring"}:
        state = "ready_now"
        risk = "low"
        estimated_new_code = "small wrapper or report configuration"
        time_to_prototype = "same_day"
        work_type = "reusable"
        deployment = "local Python CLI/report"
        add_adjust("ready_reusable_work", 0.12, "matches existing local report/scanner capabilities")
    elif deliverable == "workflow_or_webhook_automation":
        state = "mostly_ready"
        risk = "medium"
        estimated_new_code = "adapter/config plus tests"
        time_to_prototype = "1-3_days"
        work_type = "reusable"
        deployment = "local script plus customer platform configuration"
        external.extend([p for p in platforms if p in {"n8n", "zapier", "make", "airtable", "notion"}])
        if external:
            human_setup.append("customer platform access or exported workflow details")
            add_adjust("external_workflow_platform", -0.08, "requires third-party platform details/access")
    elif deliverable == "gohighlevel_operations_automation":
        state = "partial"
        risk = "medium"
        estimated_new_code = "workflow plan plus possible API adapter"
        time_to_prototype = "2-5_days"
        work_type = "partly_reusable"
        deployment = "GoHighLevel account/workflow environment"
        external.append("GoHighLevel")
        human_setup.append("client GoHighLevel access, sample pipeline, and approval")
        missing.append("verified GoHighLevel integration module")
        add_adjust("unsupported_specific_platform", -0.14, "Echo has workflow skills but no verified GoHighLevel adapter")
    elif deliverable == "ai_video_workflow":
        state = "partial"
        risk = "medium"
        estimated_new_code = "workflow orchestration prototype"
        time_to_prototype = "3-7_days"
        work_type = "partly_reusable"
        deployment = "external AI video/avatar tools plus local orchestration"
        external.extend(["AI avatar/video services", "media rendering tools"])
        human_setup.append("tool accounts, sample assets, output quality review")
        missing.append("verified video generation/editing pipeline")
        add_adjust("media_pipeline_gap", -0.12, "Echo lacks a verified video production pipeline")
    elif deliverable == "custom_app_or_backend_development":
        state = "major_gap"
        risk = "high"
        estimated_new_code = "full custom application"
        time_to_prototype = "1-3_weeks"
        work_type = "one_off"
        deployment = "customer web/app hosting environment"
        missing.extend(["product requirements", "deployment target", "auth/data model", "maintenance plan"])
        human_setup.append("ongoing customer communication and scope control")
        add_adjust("full_product_gap", -0.28, "full app/team work is beyond current packaged Echo delivery")
    elif deliverable == "game_or_emulator_automation":
        state = "incompatible_or_unsafe"
        risk = "critical"
        estimated_new_code = "not recommended"
        time_to_prototype = "not_applicable"
        work_type = "unsafe_or_tos_risk"
        deployment = "emulators/game accounts"
        external.extend(["game client", "emulator", "multiple accounts"])
        missing.append("safe/allowed use case")
        add_adjust("tos_or_abuse_risk", -0.50, "game/emulator automation can violate platform rules")
    elif deliverable == "human_sales_or_appointment_setting":
        state = "major_gap"
        risk = "high"
        estimated_new_code = "not primarily software"
        time_to_prototype = "not_applicable"
        work_type = "human_service"
        deployment = "human communication channel"
        human_setup.append("live sales calls/messages and personal representation")
        missing.append("human sales operator")
        add_adjust("human_service_gap", -0.30, "requires ongoing human communication, not a local automation deliverable")
    elif deliverable == "content_writing_or_marketing":
        state = "mostly_ready" if primary_label == "hiring_request" else "partial"
        risk = "medium"
        estimated_new_code = "little to none; content workflow configuration"
        time_to_prototype = "same_day"
        work_type = "semi_reusable"
        deployment = "document/content delivery"
        modules.extend(["core/content_pipeline.py", "tools/newsletter_composer.py"])
        human_setup.append("style brief and approval")
        add_adjust("content_pipeline_match", 0.04, "Echo has content generation support but needs human review")
    elif deliverable == "qa_automation":
        state = "partial"
        risk = "medium"
        estimated_new_code = "test harness and project-specific adapters"
        time_to_prototype = "2-5_days"
        work_type = "partly_reusable"
        deployment = "customer repo/CI environment"
        human_setup.append("repository access and test target details")
        missing.append("customer repo access")
        add_adjust("repo_access_required", -0.10, "requires customer codebase and CI context")
    elif deliverable == "website_or_landing_page":
        state = "mostly_ready"
        risk = "medium"
        estimated_new_code = "single site/page implementation"
        time_to_prototype = "1-3_days"
        work_type = "partly_reusable"
        deployment = "static site or customer hosting"
        human_setup.append("brand/content/assets and deployment target")
        add_adjust("web_delivery_match", 0.04, "Echo can build pages but needs client assets and review")

    if term_in_text(text, "reddit commenting") or term_in_text(text, "fake installs") or term_in_text(text, "bot traffic"):
        state = "incompatible_or_unsafe"
        risk = "critical"
        missing.append("safe non-spam scope")
        add_adjust("spam_or_platform_manipulation", -0.45, "requires platform manipulation or spam-like behavior")
    if any(term_in_text(text, term) for term in ("respiratory therapist", "clinical", "medical doctor")) and primary_label == "hiring_request":
        state = "incompatible_or_unsafe"
        risk = "critical"
        missing.append("licensed human professional")
        add_adjust("licensed_profession_gap", -0.45, "not software automation work")
    if any(term_in_text(text, term) for term in ("senior", "3 5", "3 years", "full time", "long term position")) and primary_label == "hiring_request":
        if state not in {"incompatible_or_unsafe"}:
            state = "major_gap"
            risk = "high"
            add_adjust("full_role_penalty", -0.20, "long-term role/team requirement is not an easy automation opportunity")

    if not platforms and state in {"partial", "unclear"}:
        add_adjust("unclear_platform_penalty", -0.08, "platform/API requirements are unclear")
    if primary_label == "hiring_request" and state in {"major_gap", "incompatible_or_unsafe"}:
        add_adjust("major_gap_hiring_penalty", -0.18, "high-intent hiring post requires capability Echo cannot safely satisfy now")
    if work_type == "reusable":
        add_adjust("reuse_bonus", 0.05, "deliverable can become a reusable product/service pattern")
    if primary_label != "direct_buyer_request":
        add_adjust("not_direct_buyer_penalty", -0.08, "not a direct buyer project request")

    score = STATE_SCORES[state] + sum(float(item["delta"]) for item in adjustments)
    score = round(max(0.0, min(1.0, score)), 3)

    return {
        "requested_deliverable": deliverable,
        "required_platforms_apis": sorted(set(platforms + external)),
        "required_technical_skills": sorted(set(skills)),
        "required_human_communication": human_setup,
        "expected_deployment_environment": deployment,
        "likely_security_or_account_access_requirements": account_requirements_for(platforms, deliverable, primary_label),
        "work_type": work_type,
        "buyer_readiness_evidence": buyer_readiness_evidence(text),
        "capability_state": state,
        "capability_match_score": score,
        "reusable_existing_modules": sorted(set(modules)),
        "missing_components": sorted(set(missing)),
        "estimated_new_code": estimated_new_code,
        "external_dependencies": sorted(set(external)),
        "human_setup_required": human_setup,
        "delivery_risk": risk,
        "estimated_time_to_prototype": time_to_prototype,
        "fit_reason": fit_reason(state, deliverable, modules, missing, external),
        "capability_score_adjustments": adjustments,
    }


def buyer_readiness_evidence(text: str) -> list[str]:
    evidence = []
    for pattern in ("budget", "fixed budget", "$", "per hour", "per month", "asap", "urgent", "apply", "dm me", "message me"):
        if pattern == "$":
            if "$" in text:
                evidence.append("dollar amount")
        elif term_in_text(text, pattern):
            evidence.append(pattern)
    return evidence


def account_requirements_for(platforms: list[str], deliverable: str, primary_label: str) -> list[str]:
    requirements = []
    for platform in platforms:
        if platform in {"gohighlevel", "n8n", "zapier", "make", "airtable", "notion", "quickbooks", "stripe", "paypal", "whatsapp", "reddit", "claude", "openai"}:
            requirements.append(f"{platform} access or exported config")
    if deliverable in {"custom_app_or_backend_development", "qa_automation"}:
        requirements.append("customer repository or deployment access")
    if primary_label in {"hiring_request", "partnership_request"}:
        requirements.append("human communication and acceptance process")
    return sorted(set(requirements))


def fit_reason(state: str, deliverable: str, modules: list[str], missing: list[str], external: list[str]) -> str:
    if state in {"ready_now", "mostly_ready"}:
        return f"{deliverable} overlaps existing Echo modules: {', '.join(modules[:3])}"
    if state == "partial":
        return f"{deliverable} is partly aligned, but missing {', '.join(missing[:3]) or 'verified customer-specific adapter'}"
    if state == "major_gap":
        return f"{deliverable} needs substantial human/team or product work beyond current reusable Echo modules"
    if state == "incompatible_or_unsafe":
        return f"{deliverable} has safety, platform, licensed-work, or abuse risk"
    if external:
        return f"{deliverable} depends on unclear external platforms: {', '.join(external[:3])}"
    return f"{deliverable} requirements are not clear enough to claim capability"


def final_opportunity_score(record: dict[str, Any], fit: dict[str, Any]) -> float:
    corrected = float(record.get("corrected_rank_score", record.get("rank_score", 0.0)) or 0.0)
    capability_score = float(fit.get("capability_match_score", 0.0) or 0.0)
    label = record.get("primary_label")
    risk = fit.get("delivery_risk")
    state = fit.get("capability_state")
    work_type = fit.get("work_type")

    score = corrected * 0.55 + capability_score * 0.35
    if label == "direct_buyer_request":
        score += 0.06
    elif label == "hiring_request":
        score -= 0.10
    elif label == "partnership_request":
        score -= 0.18
    elif label == "advice_request":
        score -= 0.15
    else:
        score -= 0.22
    if work_type == "reusable":
        score += 0.04
    elif work_type in {"one_off", "human_service", "unsafe_or_tos_risk"}:
        score -= 0.06
    if risk == "high":
        score -= 0.08
    elif risk == "critical":
        score -= 0.18
    if fit.get("external_dependencies"):
        score -= min(0.08, len(fit["external_dependencies"]) * 0.025)
    if fit.get("human_setup_required"):
        score -= min(0.06, len(fit["human_setup_required"]) * 0.02)

    if state == "incompatible_or_unsafe":
        score = min(score, 0.16)
    elif state == "major_gap":
        score = min(score, 0.42)
    elif state == "unclear":
        score = min(score, 0.38)
    elif state == "partial":
        score = min(score, 0.72)

    if label == "hiring_request":
        score = min(score, 0.42)
    elif label == "partnership_request":
        score = min(score, 0.42)
    elif label not in {"direct_buyer_request", "hiring_request", "partnership_request"}:
        score = min(score, 0.34)

    return round(max(0.0, min(1.0, score)), 4)


def classify_intent(lead: dict[str, Any], now: datetime, stale_days: int) -> dict[str, Any]:
    text = norm_text(lead_text(lead))
    title = norm_text(str(lead.get("title", "") or ""))
    subreddit = norm_text(str(lead.get("subreddit", "") or ""))
    ts = parse_time(lead.get("found_at") or lead.get("timestamp") or lead.get("created_at"))
    age_days = (now - ts).days if ts else None
    stale = bool(age_days is None or age_days > stale_days)

    evidence: list[str] = []
    buyer_hits = matches(text, BUYER_PATTERNS)
    if re.search(r"\b(my budget is|budget is|budget available|budget:|\$\d+)", text):
        buyer_hits.append("explicit budget")
    job_hits = matches(text, JOB_PATTERNS)
    advice_hits = matches(text, ADVICE_PATTERNS)
    promo_hits = matches(text, PROMO_PATTERNS)
    spam_hits = matches(text, SPAM_PATTERNS)
    problem_hits = matches(text, PROBLEM_PATTERNS)
    complaint_hits = matches(text, COMPLAINT_PATTERNS)
    urgent_hits = matches(text, URGENT_PATTERNS)

    strong_buyer_hits = [hit for hit in buyer_hits if hit not in {"explicit budget"}]

    if spam_hits:
        intent = "spam_promotion"
        evidence.append(f"spam/promo terms: {', '.join(spam_hits[:4])}")
    elif promo_hits and not strong_buyer_hits:
        intent = "spam_promotion"
        evidence.append(f"promotion/showcase terms: {', '.join(promo_hits[:4])}")
    elif job_hits and ("forhire" in text or "hiring" in title or "[hiring]" in title):
        intent = "job_opportunity"
        evidence.append(f"job terms: {', '.join(job_hits[:4])}")
    elif buyer_hits:
        intent = "buyer_intent"
        evidence.append(f"buyer terms: {', '.join(buyer_hits[:4])}")
    elif advice_hits:
        intent = "advice_request"
        evidence.append(f"advice terms: {', '.join(advice_hits[:4])}")
    elif complaint_hits:
        intent = "complaint"
        evidence.append(f"complaint terms: {', '.join(complaint_hits[:4])}")
    elif problem_hits:
        intent = "genuine_problem_need"
        evidence.append(f"problem terms: {', '.join(problem_hits[:4])}")
    elif "?" in str(lead.get("title", "")) or "discussion" in text:
        intent = "casual_discussion"
        evidence.append("question/discussion language without clear buyer evidence")
    else:
        intent = "unclear_intent"
        evidence.append("no strong deterministic intent evidence")

    if stale:
        evidence.append(f"stale: age_days={age_days}")

    capability, capability_score, capability_evidence = capability_match(text)
    if capability_evidence:
        evidence.append(f"capability terms: {', '.join(capability_evidence[:5])}")

    buyer_score = 0.0
    if intent == "buyer_intent":
        buyer_score = 0.75 + min(len(buyer_hits), 4) * 0.05
    elif intent == "job_opportunity":
        buyer_score = 0.65
    elif intent == "genuine_problem_need":
        buyer_score = 0.35
    elif intent in {"advice_request", "complaint"}:
        buyer_score = 0.22
    elif intent == "casual_discussion":
        buyer_score = 0.08
    elif intent == "spam_promotion":
        buyer_score = 0.02
    else:
        buyer_score = 0.12

    urgency = 0.15
    if urgent_hits:
        urgency += 0.45
        evidence.append(f"urgency terms: {', '.join(urgent_hits[:4])}")
    if buyer_hits:
        urgency += 0.2
    if "forhire" in text or "hiring" in text:
        urgency += 0.15
    if stale:
        urgency *= 0.35

    effort = estimate_effort(text, capability)
    mission = mission_alignment(intent, capability)
    reuse = reuse_potential(text, capability)
    confidence = confidence_score(intent, evidence, ts, stale)
    freshness = freshness_score(age_days)

    original_rank_score = rank_score(
        buyer_intent=buyer_score,
        urgency=urgency,
        capability=capability_score,
        effort=effort,
        reuse=reuse,
        mission=mission,
        confidence=confidence,
        freshness=freshness,
    )
    features = ambiguity_features(text, title, subreddit)
    primary_label = primary_label_for(intent, features, text, subreddit)
    adjustments = score_adjustments_for(primary_label, features)
    corrected_rank_score = apply_score_correction(original_rank_score, adjustments)
    fit = capability_fit_for(text, title, primary_label, capability, features)

    if primary_label in {
        "research_about_demand",
        "tutorial_or_showcase",
        "self_promotion",
        "general_discussion",
        "spam_or_low_signal",
        "unclear",
    }:
        buyer_score = min(buyer_score, 0.18)
    elif primary_label == "hiring_request":
        buyer_score = min(buyer_score, 0.58)
    elif primary_label == "partnership_request":
        buyer_score = min(buyer_score, 0.35)

    record = {
        "lead_id": lead_id(lead),
        "source": lead.get("subreddit") or lead.get("source") or "unknown",
        "timestamp": lead.get("found_at") or lead.get("timestamp") or lead.get("created_at"),
        "problem_summary": problem_summary(lead),
        "intent_class": "stale_lead" if stale and intent == "unclear_intent" else intent,
        "primary_label": primary_label,
        "requester_vs_provider_orientation": features["requester_vs_provider_orientation"],
        "ambiguity_features": features,
        "buyer_intent_score": round(min(1.0, buyer_score), 3),
        "urgency_score": round(min(1.0, urgency), 3),
        "confidence": round(confidence, 3),
        "estimated_effort": round(effort, 3),
        "existing_capability_match": capability,
        "existing_capability_score": capability_score,
        "mission_alignment": round(mission, 3),
        "reuse_potential": round(reuse, 3),
        "duplicate_cluster_id": "",
        "stale": stale,
        "age_days": age_days,
        "evidence": evidence[:8],
        "score_adjustments": adjustments,
        "original_rank_score": original_rank_score,
        "corrected_rank_score": corrected_rank_score,
        "recommended_action": recommended_action(primary_label, stale, capability, confidence),
        "rank_score": corrected_rank_score,
        "url": lead.get("url"),
        "raw_score": lead.get("score"),
    }
    record.update(fit)
    record["intent_rank_score"] = corrected_rank_score
    record["final_opportunity_score"] = final_opportunity_score(record, fit)
    return record


def estimate_effort(text: str, capability: str) -> float:
    effort = 0.45
    if capability in {"workflow_automation", "data_reporting", "demand_intent_monitoring"}:
        effort -= 0.15
    if capability in {"local_ai_tooling", "system_reliability"}:
        effort += 0.1
    if any(term in text for term in ("enterprise", "mobile app", "ios", "android", "production", "scale", "multi tenant")):
        effort += 0.25
    if any(term in text for term in ("csv", "script", "small", "simple", "local", "spreadsheet")):
        effort -= 0.12
    return max(0.05, min(1.0, effort))


def mission_alignment(intent: str, capability: str) -> float:
    score = 0.35
    if capability in {"demand_intent_monitoring", "workflow_automation", "data_reporting", "local_ai_tooling"}:
        score += 0.35
    if intent in {"buyer_intent", "genuine_problem_need", "job_opportunity"}:
        score += 0.2
    if intent == "spam_promotion":
        score -= 0.25
    return max(0.0, min(1.0, score))


def reuse_potential(text: str, capability: str) -> float:
    score = 0.3
    if capability in {"demand_intent_monitoring", "workflow_automation", "data_reporting"}:
        score += 0.3
    if any(term in text for term in ("small business", "reddit", "csv", "dashboard", "automation", "workflow", "api")):
        score += 0.25
    if any(term in text for term in ("custom only", "one-off", "co-founder", "equity")):
        score -= 0.2
    return max(0.0, min(1.0, score))


def confidence_score(intent: str, evidence: list[str], ts: datetime | None, stale: bool) -> float:
    score = 0.35 + min(len(evidence), 5) * 0.08
    if intent in {"buyer_intent", "job_opportunity", "spam_promotion"}:
        score += 0.15
    if intent == "unclear_intent":
        score -= 0.2
    if not ts:
        score -= 0.1
    if stale:
        score -= 0.15
    return max(0.05, min(1.0, score))


def freshness_score(age_days: int | None) -> float:
    if age_days is None:
        return 0.1
    if age_days <= 7:
        return 1.0
    if age_days <= 30:
        return 0.75
    if age_days <= 90:
        return 0.45
    if age_days <= 180:
        return 0.2
    return 0.05


def rank_score(
    buyer_intent: float,
    urgency: float,
    capability: float,
    effort: float,
    reuse: float,
    mission: float,
    confidence: float,
    freshness: float,
) -> float:
    effort_fit = 1.0 - effort
    score = (
        buyer_intent * 0.24
        + urgency * 0.14
        + capability * 0.16
        + effort_fit * 0.12
        + reuse * 0.12
        + mission * 0.12
        + confidence * 0.06
        + freshness * 0.04
    )
    return round(max(0.0, min(1.0, score)), 4)


def recommended_action(primary_label: str, stale: bool, capability: str, confidence: float) -> str:
    if stale:
        return "preserve_for_audit_revalidate_before_action"
    if confidence < 0.35:
        return "preserve_low_confidence_review_later"
    if primary_label in {
        "research_about_demand",
        "tutorial_or_showcase",
        "self_promotion",
        "general_discussion",
        "spam_or_low_signal",
        "unclear",
    }:
        return "do_not_act_use_as_market_signal_only"
    if primary_label in {"hiring_request", "partnership_request", "advice_request"}:
        return "review_manually_before_any_build_or_outreach"
    if capability == "missing_capability":
        return "review_manually_before_any_build"
    return "candidate_for_productized_solution_design"


def cluster_key(record: dict[str, Any]) -> str:
    summary = norm_text(record.get("problem_summary", ""))
    words = [w for w in summary.split() if len(w) > 3 and w not in {"looking", "someone", "built", "with", "that", "this", "from"}]
    basis = " ".join(words[:10]) or summary[:80] or record["lead_id"]
    raw = f"{record.get('intent_class')}:{record.get('existing_capability_match')}:{basis}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def apply_clusters(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    for record in records:
        cid = cluster_key(record)
        record["duplicate_cluster_id"] = cid
        seen[cid] = seen.get(cid, 0) + 1
    for record in records:
        count = seen.get(record["duplicate_cluster_id"], 1)
        if count > 1 and record["intent_class"] not in {"spam_promotion", "stale_lead"}:
            record["evidence"] = [*record["evidence"], f"duplicate cluster size={count}"][:8]
        record["cluster_size"] = count
    return records


def cluster_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["duplicate_cluster_id"]].append(record)

    candidates = []
    for cid, items in groups.items():
        items.sort(key=lambda item: item.get("final_opportunity_score", item["rank_score"]), reverse=True)
        best = items[0]
        duplicate_penalty = min(0.12, max(0, len(items) - 1) * 0.015)
        cluster_score = round(max(0.0, best.get("final_opportunity_score", best["rank_score"]) - duplicate_penalty), 4)
        candidates.append({
            "candidate_id": f"demand-{cid}",
            "duplicate_cluster_id": cid,
            "cluster_size": len(items),
            "rank_score": cluster_score,
            "final_opportunity_score": cluster_score,
            "representative_lead_id": best["lead_id"],
            "lead_ids": [item["lead_id"] for item in items[:25]],
            "source_mix": dict(Counter(str(item.get("source", "unknown")) for item in items).most_common(6)),
            "intent_class": best["intent_class"],
            "primary_label": best["primary_label"],
            "requester_vs_provider_orientation": best["requester_vs_provider_orientation"],
            "problem_summary": best["problem_summary"],
            "buyer_intent_score": best["buyer_intent_score"],
            "urgency_score": best["urgency_score"],
            "confidence": best["confidence"],
            "estimated_effort": best["estimated_effort"],
            "existing_capability_match": best["existing_capability_match"],
            "mission_alignment": best["mission_alignment"],
            "reuse_potential": best["reuse_potential"],
            "stale": best["stale"],
            "evidence": best["evidence"][:8],
            "ambiguity_features": best["ambiguity_features"],
            "score_adjustments": best["score_adjustments"],
            "original_rank_score": best["original_rank_score"],
            "corrected_rank_score": best["corrected_rank_score"],
            "intent_rank_score": best.get("intent_rank_score", best["corrected_rank_score"]),
            "requested_deliverable": best["requested_deliverable"],
            "required_platforms_apis": best["required_platforms_apis"],
            "required_technical_skills": best["required_technical_skills"],
            "required_human_communication": best["required_human_communication"],
            "expected_deployment_environment": best["expected_deployment_environment"],
            "likely_security_or_account_access_requirements": best["likely_security_or_account_access_requirements"],
            "work_type": best["work_type"],
            "buyer_readiness_evidence": best["buyer_readiness_evidence"],
            "capability_state": best["capability_state"],
            "capability_match_score": best["capability_match_score"],
            "reusable_existing_modules": best["reusable_existing_modules"],
            "missing_components": best["missing_components"],
            "estimated_new_code": best["estimated_new_code"],
            "external_dependencies": best["external_dependencies"],
            "human_setup_required": best["human_setup_required"],
            "delivery_risk": best["delivery_risk"],
            "estimated_time_to_prototype": best["estimated_time_to_prototype"],
            "fit_reason": best["fit_reason"],
            "capability_score_adjustments": best["capability_score_adjustments"],
            "recommended_action": best["recommended_action"],
            "ranking_explanation": ranking_explanation(best, cluster_score, duplicate_penalty),
            "url": best.get("url"),
        })
    candidates.sort(key=lambda item: item["final_opportunity_score"], reverse=True)
    return candidates


def ranking_explanation(record: dict[str, Any], score: float, duplicate_penalty: float) -> str:
    adjustments = sum(float(item.get("delta", 0.0)) for item in record.get("score_adjustments", []))
    return (
        f"final={score:.3f}; original_intent={record.get('original_rank_score', score):.3f}, "
        f"corrected_intent={record.get('corrected_rank_score', score):.3f}, "
        f"capability_fit={record.get('capability_match_score', 0):.2f}, "
        f"capability_state={record.get('capability_state')}, "
        f"adjustments={adjustments:.2f}, label={record.get('primary_label')}; "
        f"buyer={record['buyer_intent_score']:.2f}, "
        f"urgency={record['urgency_score']:.2f}, capability={record['existing_capability_score']:.2f}, "
        f"effort_fit={1 - record['estimated_effort']:.2f}, reuse={record['reuse_potential']:.2f}, "
        f"mission={record['mission_alignment']:.2f}, confidence={record['confidence']:.2f}, "
        f"freshness={freshness_score(record.get('age_days')):.2f}, duplicate_penalty={duplicate_penalty:.2f}"
    )


def filter_leads(leads: list[dict[str, Any]], days: int, limit: int, now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=max(0, days))
    filtered = []
    for lead in leads:
        ts = parse_time(lead.get("found_at") or lead.get("timestamp") or lead.get("created_at"))
        if ts and ts < cutoff:
            continue
        filtered.append(lead)
        if len(filtered) >= limit:
            break
    return filtered


def optional_local_model_status(use_local_model: bool, model_name: str = "qwen2.5:7b") -> dict[str, Any]:
    if not use_local_model:
        return {"enabled": False, "status": "not_requested"}
    if not shutil.which("ollama"):
        return {"enabled": False, "status": "unavailable", "reason": "ollama command not found", "model": model_name}
    return {
        "enabled": False,
        "status": "available_but_not_used_in_prototype",
        "reason": "prototype keeps scoring deterministic; future pass may call local model with tight timeout",
        "model": model_name,
    }


def run(
    limit: int = DEFAULT_LIMIT,
    days: int = DEFAULT_DAYS,
    print_summary: bool = False,
    use_local_model: bool = False,
    leads_path: Path = LEADS_PATH,
    candidates_path: Path = CANDIDATES_PATH,
    report_path: Path = REPORT_PATH,
    now: datetime | None = None,
    write: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    leads = load_leads(leads_path)
    sampled = filter_leads(leads, days=days, limit=limit, now=now)
    records = [classify_intent(lead, now=now, stale_days=days) for lead in sampled]
    apply_clusters(records)
    candidates = cluster_candidates(records)
    status_counts = Counter(record["intent_class"] for record in records)
    capability_counts = Counter(record["existing_capability_match"] for record in records)
    model_status = optional_local_model_status(use_local_model)

    candidate_payload = {
        "updated_at": utcnow(),
        "source": str(leads_path.relative_to(BASE)) if leads_path.is_relative_to(BASE) else str(leads_path),
        "prototype": True,
        "bounded": {"limit": limit, "days": days, "processed": len(sampled), "available": len(leads)},
        "ranking_formula": RANKING_FORMULA,
        "model_status": model_status,
        "candidates": candidates[:50],
        "classified_leads": records,
    }
    report = {
        "updated_at": candidate_payload["updated_at"],
        "source": candidate_payload["source"],
        "processed_count": len(sampled),
        "available_count": len(leads),
        "candidate_count": len(candidates),
        "intent_counts": dict(status_counts.most_common()),
        "capability_counts": dict(capability_counts.most_common()),
        "top_5": candidates[:5],
        "low_confidence_count": sum(1 for record in records if record["confidence"] < 0.35),
        "stale_count": sum(1 for record in records if record["stale"]),
        "duplicate_cluster_count": len({record["duplicate_cluster_id"] for record in records}),
        "raw_duplicate_observation_count": len(records),
        "model_status": model_status,
    }

    if write:
        atomic_write_json(candidates_path, candidate_payload)
        atomic_write_json(report_path, report)

    if print_summary:
        print_top(candidates[:5])

    return {"candidates_payload": candidate_payload, "report": report}


RANKING_FORMULA = {
    "buyer_intent": 0.24,
    "urgency": 0.14,
    "capability_match": 0.16,
    "effort_fit": 0.12,
    "reuse_potential": 0.12,
    "mission_alignment": 0.12,
    "confidence": 0.06,
    "freshness": 0.04,
    "notes": "effort_fit = 1 - estimated_effort; duplicate clusters receive up to 0.12 score penalty.",
}


def print_top(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        print("No demand intent candidates found.")
        return
    print("Top demand intent opportunities:")
    for idx, item in enumerate(candidates, 1):
        print(
            f"{idx}. {item['rank_score']:.3f} "
            f"[{item['primary_label']}/{item['capability_state']}/{item['existing_capability_match']}] "
            f"{item['problem_summary'][:120]}"
        )
        print(f"   action={item['recommended_action']} cluster={item['cluster_size']} lead={item['representative_lead_id']}")


def self_test() -> dict[str, Any]:
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    leads = [
        {
            "post_id": "buyer-1",
            "title": "Need someone to automate CSV cleanup this week",
            "subreddit": "r/automation",
            "body": "Budget available. I need someone to build a Python script for messy spreadsheet exports.",
            "found_at": "2026-07-12T12:00:00+00:00",
            "score": 10,
        },
        {
            "post_id": "casual-1",
            "title": "What is your favorite automation idea?",
            "subreddit": "r/SideProject",
            "body": "Just curious what people like discussing.",
            "found_at": "2026-07-12T13:00:00+00:00",
            "score": 8,
        },
        {
            "post_id": "stale-1",
            "title": "Need help with Zapier workflow",
            "subreddit": "r/zapier",
            "body": "Looking for someone to fix this.",
            "found_at": "2026-01-01T00:00:00+00:00",
            "score": 9,
        },
    ]
    records = [classify_intent(lead, now=now, stale_days=30) for lead in leads]
    apply_clusters(records)
    candidates = cluster_candidates(records)
    assertions = {
        "buyer_scores_higher": records[0]["buyer_intent_score"] > records[1]["buyer_intent_score"],
        "casual_not_buyer": records[1]["intent_class"] in {"casual_discussion", "advice_request"},
        "stale_penalized": records[2]["stale"] and records[2]["rank_score"] < records[0]["rank_score"],
        "model_fallback": optional_local_model_status(True, "definitely-missing-model").get("status") in {
            "unavailable",
            "available_but_not_used_in_prototype",
        },
        "candidates_ranked": bool(candidates) and candidates[0]["representative_lead_id"] == "buyer-1",
    }
    return {
        "ok": all(assertions.values()),
        "assertions": assertions,
        "top": candidates[0] if candidates else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--use-local-model", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        if args.print:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    run(
        limit=max(1, args.limit),
        days=max(0, args.days),
        print_summary=args.print,
        use_local_model=args.use_local_model,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
