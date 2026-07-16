from __future__ import annotations

import json
from pathlib import Path

from assets.asset_database import AssetDatabase
from assets.asset_manager import AssetManager, run_fixture
from assets.asset_types import Asset, Observation


FIXTURE = Path("tests/fixtures/asset_intelligence/tacoma_day5_fixture.json")


def manager(tmp_path: Path) -> AssetManager:
    return AssetManager(AssetDatabase(tmp_path / "assets.sqlite"))


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_asset_creation_and_loading(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))

    asset = mgr.db.get_asset("TACOMA-DAY5")

    assert asset["asset_id"] == "TACOMA-DAY5"
    assert asset["type"] == "vehicle"


def test_observation_persistence_and_provenance(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))

    result = mgr.ingest_structured_observation(data["observations"][0])
    stored = mgr.db.recent_observations(asset_id="TACOMA-DAY5", limit=1)[0]

    assert result["ok"] is True
    assert stored["payload"]["provenance"]["observer"] == "FixtureReviewer"
    assert stored["payload"]["provenance"]["raw_input_reference"].endswith("tacoma_manual_note_001.txt")


def test_duplicate_observation_rejection(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))

    first = mgr.ingest_structured_observation(data["observations"][0])
    second = mgr.ingest_structured_observation(data["observations"][0])

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert len(mgr.db.recent_observations(asset_id="TACOMA-DAY5", limit=10)) == 1


def test_fact_and_inference_separation(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))
    mgr.ingest_structured_observation(data["observations"][0])
    stored = mgr.db.recent_observations(asset_id="TACOMA-DAY5", limit=1)[0]

    payload = stored["payload"]

    assert "extracted_facts" in payload
    assert "inferred_facts" in payload
    assert payload["extracted_facts"]["odometer_miles"] == 185000
    assert payload["inferred_facts"]["affected_area"] == "drivetrain_or_engine"


def test_first_observation_behavior(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))

    result = mgr.ingest_structured_observation(data["observations"][0])

    assert result["change_status"] == "no_prior_observation"
    assert "baseline" in result["comparison"]["reason"].lower()


def test_meaningful_change_detection(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))
    mgr.ingest_structured_observation(data["observations"][0])

    result = mgr.ingest_structured_observation(data["observations"][1])

    assert result["change_status"] == "changed"
    assert "symptoms" in result["comparison"]["changed_fields"]
    assert "Schedule a maintenance check" in result["recommended_next_action"]


def test_uncertain_or_conflicting_case(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))
    mgr.ingest_structured_observation(data["observations"][0])
    mgr.ingest_structured_observation(data["observations"][1])

    result = mgr.ingest_structured_observation(data["observations"][2])

    assert result["change_status"] == "conflicting_evidence"
    assert "odometer_miles" in result["comparison"]["conflicting_fields"]
    assert result["recommended_next_action"] == data["expected"]["final_next_action"]


def test_bounded_next_action_generation(tmp_path):
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))

    result = mgr.ingest_structured_observation(data["observations"][0])

    assert "order" not in result["recommended_next_action"].lower()
    assert "contact" not in result["recommended_next_action"].lower()


def test_no_direct_executive_context_mutation(tmp_path):
    exec_path = Path("memory/executive_context.json")
    before = exec_path.read_text() if exec_path.exists() else None

    run_fixture(FIXTURE, db_path=tmp_path / "assets.sqlite")

    after = exec_path.read_text() if exec_path.exists() else None
    assert after == before


def test_no_autonomous_execution(tmp_path):
    result = run_fixture(FIXTURE, db_path=tmp_path / "assets.sqlite")

    assert result["results"][-1]["recommended_next_action"].startswith("Mark for human review")
    assert result["status"]["open_tasks"] == []


def fixture_manager_with_observations(tmp_path: Path) -> tuple[AssetManager, list[dict]]:
    data = load_fixture()
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(**data["asset"]))
    results = [mgr.ingest_structured_observation(item) for item in data["observations"]]
    return mgr, results


def test_valid_observation_creates_one_pending_proposal(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    observation_id = results[-1]["observation_id"]

    proposal = mgr.propose_task_from_observation(observation_id)

    assert proposal["status"] == "pending_review"
    assert proposal["asset_id"] == "TACOMA-DAY5"
    assert proposal["source_observation_id"] == observation_id
    assert proposal["proposed_title"] == "Review Tacoma maintenance record conflict"
    assert proposal["review_summary"]["observed_facts"]["odometer_miles"] == 184900


def test_duplicate_proposal_request_returns_same_proposal(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    observation_id = results[-1]["observation_id"]

    first = mgr.propose_task_from_observation(observation_id)
    second = mgr.propose_task_from_observation(observation_id)

    assert first["proposal_id"] == second["proposal_id"]
    assert len(mgr.list_task_proposals()) == 1


def test_no_task_exists_before_approval(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    mgr.propose_task_from_observation(results[-1]["observation_id"])

    assert mgr.db.open_tasks("TACOMA-DAY5") == []


def test_explicit_approval_creates_one_task(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])

    approved = mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer", notes="approved for review")
    tasks = mgr.db.open_tasks("TACOMA-DAY5")

    assert approved["status"] == "created"
    assert approved["resulting_task_id"] == tasks[0]["id"]
    assert tasks[0]["metadata"]["source_observation_id"] == results[-1]["observation_id"]
    assert tasks[0]["metadata"]["source_proposal_id"] == proposal["proposal_id"]
    assert tasks[0]["metadata"]["created_by"] == "approved_asset_bridge"
    assert tasks[0]["metadata"]["human_reviewer"] == "FixtureReviewer"


def test_repeated_approval_does_not_duplicate_task(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])

    first = mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")
    second = mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")

    assert first["resulting_task_id"] == second["resulting_task_id"]
    assert len(mgr.db.open_tasks("TACOMA-DAY5")) == 1


def test_rejection_prevents_task_creation(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])

    rejected = mgr.reject_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer", notes="not needed")

    assert rejected["status"] == "rejected"
    assert mgr.db.open_tasks("TACOMA-DAY5") == []
    try:
        mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")
    except RuntimeError as exc:
        assert "rejected" in str(exc)
    else:
        raise AssertionError("rejected proposal should not approve")


def test_changes_requested_prevents_task_creation(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])

    changed = mgr.request_task_changes(proposal["proposal_id"], reviewer="FixtureReviewer", notes="rewrite task")

    assert changed["status"] == "changes_requested"
    assert mgr.db.open_tasks("TACOMA-DAY5") == []
    try:
        mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")
    except RuntimeError as exc:
        assert "changes_requested" in str(exc)
    else:
        raise AssertionError("changes-requested proposal should not approve")


def test_missing_provenance_blocks_proposal(tmp_path):
    mgr = manager(tmp_path)
    mgr.register_asset(Asset(asset_id="TACOMA-DAY5", name="Tacoma", type="vehicle"))
    obs_id = mgr.observe(Observation(
        asset="TACOMA-DAY5",
        summary="bad observation",
        payload={"recommended_next_action": "Mark for human review."},
    ))["observation_id"]

    try:
        mgr.propose_task_from_observation(obs_id)
    except RuntimeError as exc:
        assert "provenance incomplete" in str(exc)
    else:
        raise AssertionError("missing provenance should block proposal")


def test_unsafe_unbounded_action_is_rejected(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    observation = mgr.db.get_observation(results[-1]["observation_id"])
    payload = observation["payload"]
    payload["recommended_next_action"] = "Order replacement transmission parts and contact a mechanic."
    mgr.db.update_observation_payload(
        observation["id"],
        payload,
        actor="test",
        reason="simulate unsafe action for proposal safety test",
    )

    try:
        mgr.propose_task_from_observation(observation["id"])
    except RuntimeError as exc:
        assert "unsafe or unbounded" in str(exc)
    else:
        raise AssertionError("unsafe action should block proposal")


def test_changed_source_observation_invalidates_pending_proposal(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])
    observation = mgr.db.get_observation(results[-1]["observation_id"])
    payload = observation["payload"]
    payload["recommended_next_action"] = "Verify odometer value against the dash photo."
    mgr.db.update_observation_payload(
        observation["id"],
        payload,
        actor="test",
        reason="simulate changed source observation",
    )

    shown = mgr.show_task_proposal(proposal["proposal_id"])

    assert shown["status"] == "invalidated"
    assert shown["metadata"]["source_linkage_changed"] is True


def test_existing_created_task_is_flagged_not_deleted_on_source_change(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])
    created = mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")
    task_id = created["resulting_task_id"]
    observation = mgr.db.get_observation(results[-1]["observation_id"])
    payload = observation["payload"]
    payload["recommended_next_action"] = "Verify odometer value against the dash photo."
    mgr.db.update_observation_payload(
        observation["id"],
        payload,
        actor="test",
        reason="simulate changed source observation after task creation",
    )

    shown = mgr.show_task_proposal(proposal["proposal_id"])
    task = mgr.db.get_task(task_id)

    assert shown["status"] == "invalidated"
    assert task is not None
    assert task["metadata"]["source_linkage_changed"] is True
    assert len(mgr.db.open_tasks("TACOMA-DAY5")) == 1


def test_task_bridge_does_not_mutate_executive_context(tmp_path):
    exec_path = Path("memory/executive_context.json")
    before = exec_path.read_text() if exec_path.exists() else None
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])
    mgr.approve_task_proposal(proposal["proposal_id"], reviewer="FixtureReviewer")

    after = exec_path.read_text() if exec_path.exists() else None
    assert after == before


def test_task_bridge_has_no_autonomous_execution_side_effect(tmp_path):
    mgr, results = fixture_manager_with_observations(tmp_path)
    proposal = mgr.propose_task_from_observation(results[-1]["observation_id"])

    assert proposal["status"] == "pending_review"
    assert mgr.db.open_tasks("TACOMA-DAY5") == []
