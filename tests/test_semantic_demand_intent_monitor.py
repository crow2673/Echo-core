from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools import semantic_demand_intent_monitor as monitor


NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def lead(post_id: str, title: str, body: str = "", found_at: str = "2026-07-12T12:00:00+00:00", subreddit: str = "r/automation") -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "body": body,
        "subreddit": subreddit,
        "url": f"https://reddit.com/r/test/comments/{post_id}",
        "found_at": found_at,
        "score": 9,
    }


def classify(item: dict, days: int = 90) -> dict:
    return monitor.classify_intent(item, now=NOW, stale_days=days)


def test_duplicate_leads_collapse_into_one_cluster():
    records = [
        classify(lead("a", "Need someone to automate CSV cleanup", "Budget available for a Python script.")),
        classify(lead("b", "Need someone to automate CSV cleanup", "Budget available for a Python script.")),
    ]

    monitor.apply_clusters(records)
    candidates = monitor.cluster_candidates(records)

    assert len(candidates) == 1
    assert candidates[0]["cluster_size"] == 2
    assert len(candidates[0]["lead_ids"]) == 2


def test_casual_discussion_does_not_score_as_buyer_intent():
    record = classify(lead("casual", "What is your favorite automation idea?", "Just curious what people think.", subreddit="r/SideProject"))

    assert record["intent_class"] in {"casual_discussion", "advice_request"}
    assert record["buyer_intent_score"] < 0.3
    assert record["recommended_action"] != "candidate_for_productized_solution_design"


def test_feedback_showcase_does_not_claim_buyer_intent():
    record = classify(lead(
        "feedback",
        "Shipped v1 of my dashboard. Looking for feedback",
        "I built this for myself and want beta testers.",
        subreddit="r/SideProject",
    ))

    assert record["intent_class"] == "spam_promotion"
    assert record["buyer_intent_score"] < 0.1
    assert record["recommended_action"] == "do_not_act_use_as_market_signal_only"


def test_need_someone_to_automate_scores_higher():
    buyer = classify(lead("buyer", "Need someone to automate invoice CSV cleanup", "Budget available, looking for someone this week."))
    casual = classify(lead("casual", "Automation ideas discussion", "What workflows do people like?"))

    assert buyer["primary_label"] == "direct_buyer_request"
    assert buyer["buyer_intent_score"] > casual["buyer_intent_score"]
    assert buyer["rank_score"] > casual["rank_score"]


def test_research_post_about_automation_demand_is_not_direct_buyer():
    record = classify(lead(
        "research",
        "I scraped 10k Reddit automation discussions, and I’m curious what people want to automate",
        "I wanted to figure out what people would actually be willing to pay for. Here is what I found.",
    ))

    assert record["primary_label"] == "research_about_demand"
    assert record["buyer_intent_score"] < 0.2
    assert record["rank_score"] < record["original_rank_score"]


def test_service_provider_advertising_automation_is_not_buyer():
    record = classify(lead(
        "provider",
        "Never worry about your website and automation again",
        "We build custom workflows for small businesses. Our agency handles the setup and we offer monthly support.",
        subreddit="r/nocode",
    ))

    assert record["primary_label"] == "self_promotion"
    assert record["requester_vs_provider_orientation"] == "provider"
    assert record["buyer_intent_score"] < 0.2


def test_hiring_post_stays_distinct_from_direct_project_buyer():
    record = classify(lead(
        "hiring",
        "[HIRING] Automation specialist for n8n workflow support",
        "Remote contract role. Compensation $30/hour. Apply with examples.",
        subreddit="r/forhire",
    ))

    assert record["primary_label"] == "hiring_request"
    assert record["intent_class"] == "job_opportunity"
    assert record["recommended_action"] == "review_manually_before_any_build_or_outreach"


def test_tutorial_or_showcase_receives_penalty():
    record = classify(lead(
        "tutorial",
        "How I built a real-time intent monitoring pipeline",
        "Here is the working model, what broke, and what worked after I tested it.",
    ))

    assert record["primary_label"] == "tutorial_or_showcase"
    assert record["rank_score"] < record["original_rank_score"]


def test_quoted_demand_language_does_not_transfer_intent():
    record = classify(lead(
        "quoted",
        "How I find SaaS ideas people will pay for",
        "I search Reddit comments where users ask why there is no tool for painful workflows. This is my exact process.",
        subreddit="r/SideProject",
    ))

    assert record["primary_label"] == "research_about_demand"
    assert record["ambiguity_features"]["quoted_or_reposted_demand_language"]
    assert record["buyer_intent_score"] < 0.2


def test_stale_leads_are_penalized():
    fresh = classify(lead("fresh", "Need someone to automate a spreadsheet report", "Budget available."))
    stale = classify(lead("old", "Need someone to automate a spreadsheet report", "Budget available.", found_at="2026-01-01T00:00:00+00:00"), days=30)

    assert stale["stale"] is True
    assert stale["urgency_score"] < fresh["urgency_score"]
    assert stale["rank_score"] < fresh["rank_score"]
    assert stale["recommended_action"] == "preserve_for_audit_revalidate_before_action"


def test_missing_model_falls_back_safely(monkeypatch):
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)

    status = monitor.optional_local_model_status(True, "missing-model")

    assert status["enabled"] is False
    assert status["status"] == "unavailable"


def test_repeated_runs_do_not_duplicate_candidates(tmp_path: Path):
    leads_path = tmp_path / "demand_leads.json"
    candidates_path = tmp_path / "candidates.json"
    report_path = tmp_path / "report.json"
    leads = [
        lead("a", "Need someone to automate CSV cleanup", "Budget available."),
        lead("b", "Need someone to automate CSV cleanup", "Budget available."),
    ]
    leads_path.write_text(json.dumps(leads))

    first = monitor.run(
        limit=10,
        days=90,
        leads_path=leads_path,
        candidates_path=candidates_path,
        report_path=report_path,
        now=NOW,
    )
    second = monitor.run(
        limit=10,
        days=90,
        leads_path=leads_path,
        candidates_path=candidates_path,
        report_path=report_path,
        now=NOW,
    )

    first_ids = [item["candidate_id"] for item in first["candidates_payload"]["candidates"]]
    second_ids = [item["candidate_id"] for item in second["candidates_payload"]["candidates"]]
    written = json.loads(candidates_path.read_text())

    assert first_ids == second_ids
    assert len(written["candidates"]) == 1
    assert written["candidates"][0]["cluster_size"] == 2


def test_low_confidence_inference_is_labeled():
    record = classify(lead("unclear", "Thing I was thinking about", "No concrete request here.", subreddit="r/SideProject"))

    assert record["confidence"] < 0.5
    assert record["primary_label"] in {"unclear", "general_discussion"}
    assert record["recommended_action"] in {
        "preserve_low_confidence_review_later",
        "do_not_act_use_as_market_signal_only",
    }


def test_review_fixture_labels_are_regression_examples():
    fixture = json.loads(Path("tests/fixtures/semantic_demand_review_fixture.json").read_text())
    by_id = {item["post_id"]: item["manual_label"] for item in fixture}

    assert by_id["1tjd9ma"] == "research_about_demand"
    assert by_id["1thjcus"] == "direct_buyer_request"
    assert by_id["1tjmz3s"] == "hiring_request"
    assert by_id["1tnajs3"] == "partnership_request"


def test_major_gap_high_intent_ranks_below_ready_now_request():
    major_gap = classify(lead(
        "team-app",
        "Looking for a solid team for AI app development",
        "I need a prototype, backend, mobile app, production deployment, auth, and ongoing maintenance.",
    ))
    ready = classify(lead(
        "csv",
        "Need someone to automate CSV cleanup",
        "Budget available for a local Python script that cleans spreadsheet exports and writes a report.",
    ))

    assert major_gap["capability_state"] == "major_gap"
    assert ready["capability_state"] == "ready_now"
    assert ready["final_opportunity_score"] > major_gap["final_opportunity_score"]


def test_reusable_existing_modules_improve_fit():
    record = classify(lead(
        "intent",
        "Need someone to monitor Reddit leads and export a ranked report",
        "Looking for someone to automate Reddit demand monitoring and alerts.",
    ))

    assert record["capability_state"] == "ready_now"
    assert "tools/demand_scanner.py" in record["reusable_existing_modules"]
    assert record["capability_match_score"] >= 0.8


def test_missing_credentials_or_unsupported_apis_reduce_fit():
    record = classify(lead(
        "gohighlevel",
        "[NEEDED] GoHighLevel Automation Specialist",
        "I looking for someone to build GoHighLevel workflows for onboarding, invoicing, and lead follow-up.",
    ))

    assert record["capability_state"] == "partial"
    assert "GoHighLevel" in record["external_dependencies"]
    assert record["capability_match_score"] < 0.6


def test_full_development_team_hiring_not_easy_opportunity():
    record = classify(lead(
        "senior",
        "[Hiring] Senior AI Application Developers",
        "Looking for senior developers 3-5+ YOE to build production-grade AI products full-time.",
        subreddit="r/forhire",
    ))

    assert record["primary_label"] == "hiring_request"
    assert record["capability_state"] == "major_gap"
    assert record["final_opportunity_score"] < 0.45


def test_unclear_requirements_remain_visible_but_not_first():
    unclear = classify(lead(
        "unclear-platform",
        "Need help with automation",
        "Things are manual and I need help. Not sure what tools or platform yet.",
    ))
    ready = classify(lead(
        "ready-report",
        "Need someone to automate CSV cleanup",
        "Budget available for a local Python script that cleans spreadsheet exports.",
    ))

    assert unclear["capability_state"] in {"unclear", "mostly_ready", "partial"}
    assert unclear["final_opportunity_score"] < ready["final_opportunity_score"]


def test_direct_buyer_and_hiring_remain_separate_with_fit():
    direct = classify(lead(
        "direct",
        "Need someone to automate payment reconciliation",
        "Budget available for a script that matches Stripe and PayPal exports.",
    ))
    hiring = classify(lead(
        "hiring-fit",
        "[Hiring] Automation specialist for payment workflows",
        "Remote contract role maintaining workflows long term.",
        subreddit="r/forhire",
    ))

    assert direct["primary_label"] == "direct_buyer_request"
    assert hiring["primary_label"] == "hiring_request"
    assert direct["final_opportunity_score"] > hiring["final_opportunity_score"]
