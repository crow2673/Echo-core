from __future__ import annotations

from pathlib import Path

import pytest

from assets.asset_database import AssetDatabase
from assets.observation_manager import ObservationManager


def make_manager(tmp_path: Path) -> ObservationManager:
    return ObservationManager(
        AssetDatabase(tmp_path / "observations.sqlite"),
        observations_dir=tmp_path / "observations",
        mirror_events=False,
    )


def test_manual_intake_routes_to_observation_engine(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.ingest({
        "kind": "manual",
        "asset": "OBS-MGR-01",
        "summary": "Manual note",
        "raw_text": "Manual note body",
        "tags": ["manual"],
    })

    stored = manager.db.recent_observations(asset_id="OBS-MGR-01", limit=1)[0]
    assert result["ok"] is True
    assert result["kind"] == "manual"
    assert stored["source"] == "manual"
    assert stored["summary"] == "Manual note"


def test_voice_intake_reuses_voice_adapter_and_shared_backend(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.ingest({
        "kind": "voice",
        "asset": "OBS-MGR-01",
        "transcript": "  Tacoma note from voice   ",
        "speaker": "FixtureReviewer",
    })

    stored = manager.db.recent_observations(asset_id="OBS-MGR-01", limit=1)[0]
    assert result["ok"] is True
    assert stored["source"] == "voice"
    assert stored["payload"]["speaker"] == "FixtureReviewer"
    assert stored["summary"] == "Tacoma note from voice"


def test_image_intake_reuses_image_adapter_and_shared_backend(tmp_path):
    manager = make_manager(tmp_path)
    image = tmp_path / "local_fixture_image.txt"
    image.write_text("synthetic image bytes")

    result = manager.ingest({
        "kind": "image",
        "asset": "OBS-MGR-01",
        "path": str(image),
        "summary": "Image note",
    })

    stored = manager.db.recent_observations(asset_id="OBS-MGR-01", limit=1)[0]
    assert result["ok"] is True
    assert stored["source"] == "image"
    assert stored["payload"]["path"] == str(image)
    assert stored["payload"]["bytes"] == image.stat().st_size


def test_telemetry_intake_reuses_telemetry_engine_and_mirrors_observation(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.ingest({
        "kind": "telemetry",
        "asset": "OBS-MGR-01",
        "sensor": "rpm",
        "value": 2100,
        "units": "rpm",
    })

    stored = manager.db.recent_observations(asset_id="OBS-MGR-01", limit=1)[0]
    telemetry = manager.db.telemetry_recent("OBS-MGR-01", limit=1)[0]
    assert result["ok"] is True
    assert result["telemetry_id"] == telemetry["id"]
    assert stored["source"] == "telemetry"
    assert stored["payload"]["telemetry_id"] == telemetry["id"]
    assert telemetry["sensor"] == "rpm"


def test_sensor_and_obd_are_telemetry_aliases(tmp_path):
    manager = make_manager(tmp_path)

    sensor = manager.ingest({
        "kind": "sensor",
        "asset": "OBS-MGR-01",
        "sensor": "temperature",
        "value": 72,
        "units": "F",
    })
    obd = manager.ingest({
        "kind": "obd",
        "asset": "OBS-MGR-01",
        "sensor": "engine_rpm",
        "value": 2050,
        "units": "rpm",
    })

    observations = manager.db.recent_observations(asset_id="OBS-MGR-01", limit=5)
    assert sensor["kind"] == "sensor"
    assert obd["kind"] == "obd"
    assert {item["source"] for item in observations} >= {"sensor", "obd"}


def test_manager_writes_jsonl_memory_once_per_observation(tmp_path):
    manager = make_manager(tmp_path)
    manager.ingest({"kind": "manual", "asset": "OBS-MGR-01", "summary": "one"})
    manager.ingest({"kind": "manual", "asset": "OBS-MGR-01", "summary": "two"})

    lines = (tmp_path / "observations" / "OBS-MGR-01.jsonl").read_text().splitlines()

    assert len(lines) == 2


def test_unsupported_kind_fails_cleanly(tmp_path):
    manager = make_manager(tmp_path)

    with pytest.raises(RuntimeError, match="unsupported observation kind"):
        manager.ingest({"kind": "unknown_kind", "asset": "OBS-MGR-01"})


def test_structured_asset_intelligence_routes_to_asset_manager_with_dedupe(tmp_path):
    manager = make_manager(tmp_path)
    payload = {
        "schema": "echo.asset_observation",
        "schema_version": 1,
        "kind": "system",
        "asset_id": "ECHO-PC-TEST",
        "asset": {
            "asset_id": "ECHO-PC-TEST",
            "name": "Echo PC Test",
            "type": "computer",
            "metadata": {"fixture": True},
        },
        "timestamp": "2026-07-16T08:00:00-05:00",
        "source": "system",
        "observer": "codex",
        "summary": "GPU baseline verified",
        "raw_text": "nvidia-smi works",
        "raw_input_reference": "test",
        "processing_method": "test_fixture",
        "review_status": "reviewed",
        "confidence": 0.99,
        "tags": ["asset_intelligence", "gpu"],
        "extracted_facts": {"nvidia_driver_working": True},
        "inferred_facts": {"preserve_baseline": True},
        "uncertainty": [],
        "recommended_next_action": "Preserve the working NVIDIA baseline before changing GPU configuration.",
    }

    first = manager.ingest(payload)
    second = manager.ingest(payload)
    observations = manager.db.recent_observations(asset_id="ECHO-PC-TEST", limit=10)
    asset = manager.db.get_asset("ECHO-PC-TEST")

    assert first["structured"] is True
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert len(observations) == 1
    assert observations[0]["payload"]["extracted_facts"]["nvidia_driver_working"] is True
    assert asset["metadata"]["fixture"] is True


def test_structured_asset_intelligence_compares_against_prior(tmp_path):
    manager = make_manager(tmp_path)
    base = {
        "schema": "echo.asset_observation",
        "schema_version": 1,
        "kind": "system",
        "asset_id": "ECHO-PC-TEST",
        "asset": {"asset_id": "ECHO-PC-TEST", "name": "Echo PC Test", "type": "computer"},
        "timestamp": "2026-07-16T08:00:00-05:00",
        "source": "system",
        "observer": "codex",
        "summary": "GPU baseline one",
        "raw_text": "usage high",
        "raw_input_reference": "test1",
        "processing_method": "test_fixture",
        "review_status": "reviewed",
        "confidence": 0.99,
        "extracted_facts": {"gpu_memory_used_mib": 10962},
        "inferred_facts": {},
        "uncertainty": [],
        "recommended_next_action": "Monitor available VRAM before GPU-heavy jobs.",
    }
    current = dict(base)
    current.update({
        "timestamp": "2026-07-16T08:10:00-05:00",
        "summary": "GPU baseline two",
        "raw_input_reference": "test2",
        "extracted_facts": {"gpu_memory_used_mib": 5602},
    })

    manager.ingest(base)
    result = manager.ingest(current)

    assert result["change_status"] == "changed"
    assert "gpu_memory_used_mib" in result["comparison"]["changed_fields"]


def test_compatibility_structured_path_is_explicitly_logged(tmp_path):
    manager = make_manager(tmp_path)
    result = manager.ingest({
        "kind": "system",
        "asset_id": "ECHO-PC-COMPAT",
        "timestamp": "2026-07-16T08:00:00-05:00",
        "source": "system",
        "observer": "codex",
        "summary": "legacy structured payload",
        "raw_input_reference": "legacy",
        "processing_method": "test_fixture",
        "review_status": "reviewed",
        "extracted_facts": {"nvidia_driver_working": True},
    })

    assert result["structured"] is True
    assert result["compatibility_path"] is True
    assert "schema='echo.asset_observation'" in result["compatibility_warning"]


def test_ordinary_observation_is_not_misrouted_to_structured_path(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.ingest({
        "kind": "manual",
        "asset": "OBS-MGR-ORDINARY",
        "summary": "ordinary note",
        "raw_text": "ordinary note",
    })

    stored = manager.db.recent_observations(asset_id="OBS-MGR-ORDINARY", limit=1)[0]
    assert "structured" not in result
    assert stored["payload"] == {}


def test_reviewed_observation_cannot_be_silently_overwritten(tmp_path):
    manager = make_manager(tmp_path)
    result = manager.ingest({
        "schema": "echo.asset_observation",
        "schema_version": 1,
        "kind": "system",
        "asset_id": "ECHO-PC-REVISION",
        "timestamp": "2026-07-16T08:00:00-05:00",
        "source": "system",
        "observer": "codex",
        "summary": "reviewed baseline",
        "raw_input_reference": "test",
        "processing_method": "test_fixture",
        "review_status": "reviewed",
        "extracted_facts": {"gpu_memory_used_mib": 5602},
    })
    observation = manager.db.get_observation(result["observation_id"])
    payload = dict(observation["payload"])
    payload["recommended_next_action"] = "Monitor available VRAM before GPU-heavy jobs."

    with pytest.raises(RuntimeError, match="reviewed observations require actor and reason"):
        manager.db.update_observation_payload(observation["id"], payload)


def test_observation_revision_retains_original_and_changed_values(tmp_path):
    manager = make_manager(tmp_path)
    result = manager.ingest({
        "schema": "echo.asset_observation",
        "schema_version": 1,
        "kind": "system",
        "asset_id": "ECHO-PC-REVISION",
        "timestamp": "2026-07-16T08:00:00-05:00",
        "source": "system",
        "observer": "codex",
        "summary": "reviewed baseline",
        "raw_input_reference": "test",
        "processing_method": "test_fixture",
        "review_status": "reviewed",
        "extracted_facts": {"gpu_memory_used_mib": 5602},
    })
    observation = manager.db.get_observation(result["observation_id"])
    original = dict(observation["payload"])
    updated = dict(original)
    updated["recommended_next_action"] = "Monitor available VRAM before GPU-heavy jobs."

    revision_id = manager.db.update_observation_payload(
        observation["id"],
        updated,
        actor="Codex",
        reason="test audited correction",
    )
    revisions = manager.db.list_observation_revisions(observation["id"])

    assert revision_id == revisions[0]["id"]
    assert revisions[0]["actor"] == "Codex"
    assert revisions[0]["reason"] == "test audited correction"
    assert revisions[0]["original_payload"] == original
    assert revisions[0]["updated_payload"] == updated
    assert "recommended_next_action" in revisions[0]["changed_fields"]


def test_self_test_exercises_all_paths():
    from assets.observation_manager import _self_test

    result = _self_test()

    assert result["ok"] is True
    assert len(result["results"]) == 4
    assert len(result["recent_observations"]) == 4
    assert len(result["telemetry"]) == 1
