#!/usr/bin/env python3
"""Bounded Day 3 unattended validation for Echo.

This is an observer, not a repair tool. It samples existing Echo state on a
fixed monotonic schedule, records failures without aborting, writes a summary,
and exits.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
MEMORY = BASE / "memory"
REPORTS = BASE / "reports"
SAMPLES_PATH = MEMORY / "day3_validation_samples.jsonl"
SUMMARY_PATH = MEMORY / "day3_validation_summary.json"
HANDOFF_PATH = MEMORY / "day3_handoff.txt"
REPORT_PATH = REPORTS / "day3_unattended_validation_20260711.md"
FIX_REPORT_PATH = REPORTS / "day3_validator_completion_fix_20260712.md"

KEY_UNITS = [
    "echo-core.service",
    "echo-core-state-writer.timer",
    "echo-heartbeat.timer",
    "echo-heartbeat.service",
    "echo-pulse.timer",
    "echo-pulse.service",
    "echo-homeostasis.timer",
    "echo-homeostasis.service",
    "echo-life-loop.timer",
    "echo-life-loop.service",
    "echo-outcome-loop.timer",
    "echo-outcome-loop.service",
    "echo-governor-v2.timer",
    "echo-self-act-worker.timer",
    "echo-telegram-intake.timer",
    "echo-codex-bus-watch.timer",
    "echo-claude-bus-watch.timer",
    "echo-conductor-agents.service",
]

CORE_SERVICES = {
    "echo-core.service",
    "echo-core-state-writer.service",
    "echo-heartbeat.service",
    "echo-pulse.service",
    "echo-homeostasis.service",
    "echo-life-loop.service",
    "echo-outcome-loop.service",
    "echo-governor-v2.service",
}

SYSTEM_HEALTH_OWNERS = {
    "homeostasis",
    "core.homeostasis",
    "tools.homeostasis_check",
    "homeostasis.test",
}

CAPABILITY_BLOCKER_ROOTS = {
    "vast_monitor_missing_vast_package",
    "fiverr_fulfiller_login_failed",
    "fiverr_inbox_login_failed",
}


class InterruptedRun(Exception):
    """Raised when the validator is asked to stop before its duration elapses."""


def _handle_stop(signum, frame) -> None:
    raise InterruptedRun(f"received signal {signum}")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}
    return default


def tail_jsonl(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return items
        lines = path.read_text(errors="replace").splitlines()[-limit:]
        for line in lines:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    items.append(value)
            except Exception:
                continue
    except Exception as exc:
        items.append({"_read_error": str(exc), "_path": str(path)})
    return items


def run_cmd(args: list[str], timeout: int = 10) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(BASE),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "args": args}


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.rename(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    tmp.rename(path)


def append_sample(sample: dict[str, Any]) -> None:
    SAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLES_PATH.open("a") as handle:
        handle.write(json.dumps(sample, sort_keys=True) + "\n")


def load_sample_runs(path: Path = SAMPLES_PATH) -> list[list[dict[str, Any]]]:
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    if not path.exists():
        return runs
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            sample = json.loads(line)
        except Exception:
            continue
        if not isinstance(sample, dict):
            continue
        if sample.get("sample_index") == 0 and current:
            runs.append(current)
            current = []
        current.append(sample)
    if current:
        runs.append(current)
    return runs


def sample_run_elapsed_seconds(samples: list[dict[str, Any]]) -> float:
    if not samples:
        return 0.0
    return float(samples[-1].get("monotonic_elapsed_seconds") or 0.0)


def select_sample_run(
    runs: list[list[dict[str, Any]]],
    expected_count: int,
    duration_seconds: float,
) -> list[dict[str, Any]]:
    if not runs:
        return []
    complete_runs = [
        run for run in runs
        if len(run) >= expected_count and sample_run_elapsed_seconds(run) + 0.001 >= duration_seconds
    ]
    if complete_runs:
        return complete_runs[-1]
    return runs[-1]


def systemctl_status() -> dict[str, Any]:
    failed = run_cmd(["systemctl", "--user", "--no-pager", "--failed"], timeout=10)
    units = {}
    for unit in KEY_UNITS:
        units[unit] = {
            "active": run_cmd(["systemctl", "--user", "is-active", unit], timeout=5),
            "failed": run_cmd(["systemctl", "--user", "is-failed", unit], timeout=5),
            "show": run_cmd(
                [
                    "systemctl",
                    "--user",
                    "show",
                    unit,
                    "--property=ActiveState,SubState,MainPID,NRestarts,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp",
                ],
                timeout=5,
            ),
        }
    return {"failed_units": failed, "key_units": units}


def ps_snapshot() -> dict[str, Any]:
    result = run_cmd(["ps", "-ef"], timeout=10)
    lines = result.get("stdout", "").splitlines() if result.get("stdout") else []
    core_daemons = [line for line in lines if "echo_core_daemon.py" in line and "grep" not in line]
    launchers = [
        line
        for line in lines
        if any(token in line for token in ("launch_agents.sh", "core.conductor", "echo_conductor"))
        and "grep" not in line
    ]
    return {
        "command": result,
        "echo_core_daemon_processes": core_daemons,
        "launcher_orchestrator_processes": launchers,
    }


def pulse_snapshot() -> dict[str, Any]:
    core_state = read_json(MEMORY / "core_state_system.json", {})
    heartbeat_entries = tail_jsonl(MEMORY / "experience_log.jsonl", limit=10)
    pulse_log = BASE / "logs" / "pulse.log"
    pulse_lines = []
    try:
        if pulse_log.exists():
            pulse_lines = pulse_log.read_text(errors="replace").splitlines()[-10:]
    except Exception as exc:
        pulse_lines = [f"read_error: {exc}"]

    workers = core_state.get("workers", {}) if isinstance(core_state, dict) else {}
    heartbeat_worker = workers.get("heartbeat", {}) if isinstance(workers, dict) else {}
    pulse_worker = workers.get("pulse", {}) if isinstance(workers, dict) else {}
    writers = {
        "pulse": ["core.pulse", "echo-pulse.service"] if pulse_worker else [],
        "heartbeat": ["tools.heartbeat", "echo-heartbeat.service"] if heartbeat_worker or heartbeat_entries else [],
    }
    return {
        "core_state_updated_at": core_state.get("updated_at") if isinstance(core_state, dict) else None,
        "heartbeat_worker": heartbeat_worker,
        "pulse_worker": pulse_worker,
        "heartbeat_recent": heartbeat_entries,
        "pulse_log_tail": pulse_lines,
        "authoritative_writers": writers,
    }


def dispatcher_snapshot() -> dict[str, Any]:
    history = read_json(MEMORY / "dispatch_history.json", {})
    if not isinstance(history, dict):
        history = {"_invalid": True, "value": history}
    recent = history.get("recent", history.get("history", []))
    if isinstance(recent, list):
        recent = recent[-20:]
    return {
        "history_keys": sorted(list(history.keys()))[:50],
        "cooldowns": history.get("cooldowns", history.get("last_run", {})),
        "recent": recent,
        "file_size": (MEMORY / "dispatch_history.json").stat().st_size if (MEMORY / "dispatch_history.json").exists() else None,
    }


def temp_artifacts() -> list[str]:
    patterns = [
        "memory/*.tmp",
        "memory/.*.tmp",
        "memory/*tmp",
        "logs/*.tmp",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(str(path.relative_to(BASE)) for path in BASE.glob(pattern))
    return sorted(set(found))


def collect_sample(index: int, started_monotonic: float) -> dict[str, Any]:
    sample = {
        "sample_index": index,
        "ts": utcnow(),
        "monotonic_elapsed_seconds": round(time.monotonic() - started_monotonic, 3),
        "errors": [],
    }
    collectors = {
        "systemctl": systemctl_status,
        "processes": ps_snapshot,
        "executive_context": lambda: read_json(MEMORY / "executive_context.json", {}),
        "homeostasis": lambda: read_json(MEMORY / "homeostasis_report.json", {}),
        "life_loop": lambda: read_json(MEMORY / "life_loop_state.json", {}),
        "outcome_loop": lambda: read_json(MEMORY / "outcome_loop_report.json", {}),
        "experience_layer": lambda: read_json(MEMORY / "experience_layer_report.json", {}),
        "experience_lessons_tail": lambda: tail_jsonl(MEMORY / "experience_lessons.jsonl", limit=20),
        "pulse": pulse_snapshot,
        "dispatcher": dispatcher_snapshot,
        "temp_artifacts": temp_artifacts,
    }
    for name, collector in collectors.items():
        try:
            sample[name] = collector()
        except Exception as exc:
            sample["errors"].append({"collector": name, "error": str(exc)})
    return sample


def parse_failed_units(sample: dict[str, Any]) -> list[str]:
    stdout = sample.get("systemctl", {}).get("failed_units", {}).get("stdout", "")
    failed = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT ") or line.startswith("0 loaded") or line.startswith("LOAD "):
            continue
        if line.startswith("●"):
            line = line[1:].strip()
        parts = line.split()
        if parts and parts[0].endswith((".service", ".timer", ".socket")):
            failed.append(parts[0])
    return failed


def unit_restarts(sample: dict[str, Any]) -> dict[str, int]:
    out = {}
    for unit, data in sample.get("systemctl", {}).get("key_units", {}).items():
        show = data.get("show", {}).get("stdout", "")
        for line in show.splitlines():
            if line.startswith("NRestarts="):
                try:
                    out[unit] = int(line.split("=", 1)[1] or 0)
                except ValueError:
                    out[unit] = 0
    return out


def unit_show_value(sample: dict[str, Any], unit: str, key: str) -> str | None:
    show = sample.get("systemctl", {}).get("key_units", {}).get(unit, {}).get("show", {}).get("stdout", "")
    for line in show.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return None


def executive_ownership_violations(context: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for event in context.get("history", [])[-100:]:
        data = event.get("data", {}) if isinstance(event, dict) else {}
        source = data.get("source")
        applied = data.get("applied_keys", [])
        if "system_health" in applied and source not in SYSTEM_HEALTH_OWNERS:
            violations.append(event)
    return violations


def lesson_is_valid(lesson: dict[str, Any]) -> bool:
    if lesson.get("source") != "outcome_loop":
        return False
    if lesson.get("outcome_state") not in {"verified_success", "verified_failure"}:
        return False
    evidence = lesson.get("evidence", {})
    if isinstance(evidence, dict) and evidence.get("relevance_status") not in {None, "relevant"}:
        return False
    return bool(lesson.get("lesson") and lesson.get("expected_result") and lesson.get("result"))


def blocker_identity(blocker: dict[str, Any]) -> tuple[Any, ...]:
    return (
        blocker.get("classification"),
        blocker.get("domain"),
        blocker.get("root_cause"),
        blocker.get("source"),
        blocker.get("target_key"),
    )


def dedupe_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        key = blocker_identity(blocker)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = dict(blocker)
            continue
        existing["raw_window_count"] = max(
            int(existing.get("raw_window_count") or 0),
            int(blocker.get("raw_window_count") or 0),
        )
        if str(blocker.get("last_seen") or "") > str(existing.get("last_seen") or ""):
            existing["last_seen"] = blocker.get("last_seen")
    return sorted(deduped.values(), key=lambda item: blocker_identity(item))


def expected_sample_count(duration_minutes: float, interval_minutes: float, once: bool = False) -> int:
    if once:
        return 1
    if duration_minutes <= 0:
        return 1
    interval = max(interval_minutes, 1 / 60)
    return max(1, math.ceil(duration_minutes / interval))


def _normalized_health(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"ok", "okay", "healthy"}:
        return "OK"
    if text in {"warning", "warn", "degraded"}:
        return "warning"
    if text in {"error", "critical", "failed", "fail"}:
        return "error"
    return str(value)


def homeostasis_core_operational_health(homeostasis: dict[str, Any]) -> str | None:
    if not isinstance(homeostasis, dict):
        return None
    anomaly_summary = homeostasis.get("anomaly_summary", {})
    if isinstance(anomaly_summary, dict) and int(anomaly_summary.get("active_core_operational_count", 0) or 0) > 0:
        health = _normalized_health(homeostasis.get("system_health") or homeostasis.get("status"))
        return "error" if health == "error" else "warning"
    for item in homeostasis.get("findings", []):
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "").lower()
        classification = item.get("classification")
        if classification == "core_operational" and severity in {"warning", "critical", "error"}:
            return "error" if severity in {"critical", "error"} else "warning"
    if any(key in homeostasis for key in ("anomaly_summary", "findings", "capability_blockers", "maintenance_findings")):
        return "OK"
    return None


def authoritative_system_health(sample: dict[str, Any]) -> str | None:
    context = sample.get("executive_context", {})
    homeostasis = sample.get("homeostasis", {})
    if isinstance(homeostasis, dict):
        core_health = homeostasis_core_operational_health(homeostasis)
        if core_health is not None:
            return core_health
    if isinstance(context, dict) and context.get("system_health") is not None:
        return _normalized_health(context.get("system_health"))
    if isinstance(homeostasis, dict):
        return _normalized_health(homeostasis.get("system_health") or homeostasis.get("status"))
    return None


def life_priority_info(sample: dict[str, Any]) -> dict[str, Any]:
    life = sample.get("life_loop", {})
    priority = life.get("current_priority") if isinstance(life, dict) else {}
    if not isinstance(priority, dict):
        priority = {}
    return {
        "kind": priority.get("kind"),
        "title": priority.get("title"),
        "reason": priority.get("reason") or priority.get("focus_reason"),
    }


def priority_indicates_health_restore(priority: dict[str, Any]) -> bool:
    fields = [
        priority.get("kind"),
        priority.get("title"),
        priority.get("reason"),
    ]
    text = " ".join(str(item or "").lower() for item in fields)
    return (
        "restore system health" in text
        or "health warning" in text
        or "system_health is not ok" in text
        or (priority.get("kind") == "reliability" and "health" in text)
    )


def life_priority_health_trace(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace = []
    consecutive = 0
    for sample in samples:
        health = authoritative_system_health(sample)
        priority = life_priority_info(sample)
        mismatch = health == "OK" and priority_indicates_health_restore(priority)
        consecutive = consecutive + 1 if mismatch else 0
        trace.append({
            "sample_index": sample.get("sample_index"),
            "authoritative_system_health": health,
            "life_loop_priority_kind": priority.get("kind"),
            "life_loop_priority_title": priority.get("title"),
            "life_loop_priority_reason": priority.get("reason"),
            "mismatch": mismatch,
            "consecutive_mismatch_count": consecutive,
        })
    return trace


def analyze(
    samples: list[dict[str, Any]],
    command_used: str,
    completed: bool,
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_meta = run_meta or {}
    issues: list[dict[str, Any]] = []
    noncore_blockers: list[dict[str, Any]] = []
    expected_count = int(run_meta.get("expected_sample_count") or len(samples) or 1)
    elapsed_seconds = float(run_meta.get("elapsed_seconds") or 0.0)
    duration_seconds = float(run_meta.get("duration_seconds") or 0.0)
    completion_reason = run_meta.get("completion_reason") or ("duration_elapsed" if completed else "interrupted")

    if completed and len(samples) < expected_count:
        completed = False
        completion_reason = "insufficient_samples"
    if completed and duration_seconds > 0 and elapsed_seconds + 0.001 < duration_seconds:
        completed = False
        completion_reason = "duration_not_elapsed"

    failed_by_sample = [parse_failed_units(sample) for sample in samples]
    failed_units = sorted(set(unit for units in failed_by_sample for unit in units))
    if failed_units:
        issues.append({"severity": "fail", "code": "failed_user_units", "evidence": failed_units})

    core_daemon_counts = [len(sample.get("processes", {}).get("echo_core_daemon_processes", [])) for sample in samples]
    core_active = [unit_show_value(sample, "echo-core.service", "ActiveState") for sample in samples]
    core_main_pids = [unit_show_value(sample, "echo-core.service", "MainPID") for sample in samples]
    if any(state != "active" for state in core_active if state is not None):
        issues.append({"severity": "fail", "code": "core_service_not_active", "evidence": core_active})
    if any(count > 1 for count in core_daemon_counts):
        issues.append({"severity": "fail", "code": "duplicate_core_daemon_processes", "evidence": core_daemon_counts})
    if any(pid in {None, "", "0"} for pid in core_main_pids):
        issues.append({"severity": "fail", "code": "core_service_missing_main_pid", "evidence": core_main_pids})

    restart_series = [unit_restarts(sample) for sample in samples]
    restart_delta = {}
    if restart_series:
        first = restart_series[0]
        last = restart_series[-1]
        for unit in set(first) | set(last):
            restart_delta[unit] = last.get(unit, 0) - first.get(unit, 0)
    restart_loops = {unit: delta for unit, delta in restart_delta.items() if delta >= 3}
    if restart_loops:
        issues.append({"severity": "fail", "code": "restart_loop", "evidence": restart_loops})

    contexts = [sample.get("executive_context", {}) for sample in samples]
    unreadable_contexts = [ctx for ctx in contexts if isinstance(ctx, dict) and ctx.get("_read_error")]
    if unreadable_contexts:
        issues.append({"severity": "fail", "code": "executive_context_unreadable", "evidence": unreadable_contexts[-1]})
    ownership = [violation for ctx in contexts for violation in executive_ownership_violations(ctx if isinstance(ctx, dict) else {})]
    if ownership:
        issues.append({"severity": "fail", "code": "executive_context_ownership_violation", "evidence": ownership[-5:]})

    health_values = [sample.get("homeostasis", {}).get("system_health") or sample.get("homeostasis", {}).get("status") for sample in samples]
    context_health = [sample.get("executive_context", {}).get("system_health") for sample in samples]
    if any(value not in {"OK", "ok"} for value in context_health if value):
        latest_ctx = samples[-1].get("executive_context", {})
        blockers = latest_ctx.get("capability_blockers", []) if isinstance(latest_ctx, dict) else []
        roots = {item.get("root_cause") for item in blockers if isinstance(item, dict)}
        if roots and roots <= CAPABILITY_BLOCKER_ROOTS:
            noncore_blockers.extend(blockers)
        else:
            issues.append({"severity": "warning", "code": "executive_context_health_not_ok", "evidence": context_health[-5:]})

    if any(value not in {"OK", "ok"} for value in health_values if value):
        latest_homeostasis = samples[-1].get("homeostasis", {})
        blockers = latest_homeostasis.get("capability_blockers", []) if isinstance(latest_homeostasis, dict) else []
        roots = {item.get("root_cause") for item in blockers if isinstance(item, dict)}
        if roots and roots <= CAPABILITY_BLOCKER_ROOTS:
            noncore_blockers.extend(blockers)
        else:
            issues.append({"severity": "warning", "code": "homeostasis_core_health_not_ok", "evidence": health_values[-5:]})

    life_titles = [
        sample.get("life_loop", {}).get("current_priority", {}).get("title")
        for sample in samples
        if isinstance(sample.get("life_loop"), dict)
    ]
    distinct_titles = [title for title in Counter(life_titles) if title]
    if len(distinct_titles) > max(3, len(samples) // 2):
        issues.append({"severity": "warning", "code": "life_loop_priority_oscillation", "evidence": life_titles})
    life_health_trace = life_priority_health_trace(samples)
    stale_health_focus = [item for item in life_health_trace if item["consecutive_mismatch_count"] >= 2]
    if stale_health_focus:
        issues.append({
            "severity": "warning",
            "code": "stale_life_loop_health_priority",
            "evidence": stale_health_focus[-5:],
        })

    pulse_ages = []
    heartbeat_ages = []
    duplicate_pulse_writers = []
    for sample in samples:
        pulse = sample.get("pulse", {})
        pulse_worker = pulse.get("pulse_worker", {})
        heartbeat_worker = pulse.get("heartbeat_worker", {})
        if pulse_worker.get("age_seconds") is not None:
            pulse_ages.append(pulse_worker.get("age_seconds"))
        if heartbeat_worker.get("age_seconds") is not None:
            heartbeat_ages.append(heartbeat_worker.get("age_seconds"))
        writers = pulse.get("authoritative_writers", {})
        if len(writers.get("pulse", [])) > 2 or len(writers.get("heartbeat", [])) > 2:
            duplicate_pulse_writers.append(writers)
    if pulse_ages and max(pulse_ages) > 36 * 60 * 60:
        issues.append({"severity": "fail", "code": "pulse_stale", "evidence": pulse_ages[-5:]})
    if heartbeat_ages and max(heartbeat_ages) > 5 * 60:
        issues.append({"severity": "fail", "code": "heartbeat_stale", "evidence": heartbeat_ages[-5:]})
    if duplicate_pulse_writers:
        issues.append({"severity": "fail", "code": "duplicate_heartbeat_or_pulse_writers", "evidence": duplicate_pulse_writers[-3:]})

    raw_outcome_signatures = [
        sample.get("outcome_loop", {}).get("executive_evidence", {}).get("outcome_evidence_signature")
        for sample in samples
        if isinstance(sample.get("outcome_loop"), dict)
    ]
    outcome_signatures = sorted(set(signature for signature in raw_outcome_signatures if signature))
    outcome_history_counts = [
        len([
            event for event in sample.get("executive_context", {}).get("history", [])
            if isinstance(event, dict) and event.get("data", {}).get("source") == "outcome_loop"
        ])
        for sample in samples
        if isinstance(sample.get("executive_context"), dict)
    ]
    if len(outcome_signatures) == 1 and outcome_history_counts:
        if outcome_history_counts[-1] - outcome_history_counts[0] > 1:
            issues.append({
                "severity": "warning",
                "code": "outcome_duplicate_evidence_noise",
                "evidence": {"signatures": raw_outcome_signatures, "history_counts": outcome_history_counts},
            })

    invalid_lessons = []
    for sample in samples:
        for lesson in sample.get("experience_lessons_tail", []):
            if isinstance(lesson, dict) and not lesson_is_valid(lesson):
                invalid_lessons.append(lesson)
    if invalid_lessons:
        issues.append({"severity": "fail", "code": "invented_or_invalid_experience_lesson", "evidence": invalid_lessons[-5:]})

    tmp = sorted(set(path for sample in samples for path in sample.get("temp_artifacts", [])))
    if tmp:
        issues.append({"severity": "warning", "code": "atomic_write_temp_artifacts", "evidence": tmp})

    sample_errors = [err for sample in samples for err in sample.get("errors", [])]
    if sample_errors:
        issues.append({"severity": "warning", "code": "sample_read_errors", "evidence": sample_errors[-10:]})

    noncore_blockers = dedupe_blockers(noncore_blockers)

    if not completed:
        classification = "INCOMPLETE"
    elif any(issue["severity"] == "fail" for issue in issues):
        classification = "FAIL"
    elif any(issue["severity"] == "warning" for issue in issues):
        classification = "WARNING"
    elif noncore_blockers:
        classification = "PASS_WITH_NONCORE_BLOCKERS"
    else:
        classification = "PASS"

    pulse_ok = not any(issue["code"] in {"pulse_stale", "heartbeat_stale", "duplicate_heartbeat_or_pulse_writers"} for issue in issues)
    new_lessons = samples[-1].get("experience_layer", {}).get("promoted_count") if samples else 0
    summary = {
        "updated_at": utcnow(),
        "classification": classification,
        "completed": completed,
        "expected_sample_count": expected_count,
        "actual_sample_count": len(samples),
        "sample_count": len(samples),
        "start_monotonic": run_meta.get("start_monotonic"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "duration_seconds": round(duration_seconds, 3),
        "completion_reason": completion_reason,
        "interruption_reason": run_meta.get("interruption_reason"),
        "service_exit_status": run_meta.get("service_exit_status"),
        "command_used": command_used,
        "issues": issues,
        "noncore_blockers": noncore_blockers,
        "failed_units": failed_units,
        "restart_delta": restart_delta,
        "life_priority_titles": life_titles,
        "life_priority_health_trace": life_health_trace,
        "pulse_healthy": pulse_ok,
        "experience_promoted_count_latest": new_lessons,
        "outcome_evidence_signatures": outcome_signatures[-10:],
        "outcome_evidence_signature_observation_count": len([sig for sig in raw_outcome_signatures if sig]),
        "pass_criteria": {
            "no_failed_user_units": not failed_units,
            "no_restart_loop": not restart_loops,
            "executive_context_readable_and_protected": not unreadable_contexts and not ownership,
            "homeostasis_core_health_ok_or_noncore_only": not any(issue["code"] == "homeostasis_core_health_not_ok" for issue in issues),
            "life_loop_not_false_health_trapped": not any(issue["code"] == "stale_life_loop_health_priority" for issue in issues),
            "echo_pulse_fresh_single_writer": pulse_ok,
            "outcome_loop_no_duplicate_evidence_noise": not any(issue["code"] == "outcome_duplicate_evidence_noise" for issue in issues),
            "experience_only_verified_relevant_lessons": not invalid_lessons,
            "no_temp_race_artifacts": not tmp,
        },
    }
    return summary


def write_report(summary: dict[str, Any], samples: list[dict[str, Any]]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    latest = samples[-1] if samples else {}
    lines = [
        "# Day 3 Unattended Validation - 2026-07-11",
        "",
        f"Overall result: `{summary['classification']}`",
        f"Completed: `{summary['completed']}`",
        f"Samples: `{summary['actual_sample_count']}` / expected `{summary['expected_sample_count']}`",
        f"Elapsed seconds: `{summary['elapsed_seconds']}` / duration `{summary['duration_seconds']}`",
        f"Completion reason: `{summary['completion_reason']}`",
        f"Command/service used: `{summary['command_used']}`",
        "",
        "## Current State",
        f"- failed user units: `{summary['failed_units']}`",
        f"- pulse healthy: `{summary['pulse_healthy']}`",
        f"- latest Experience promoted count: `{summary['experience_promoted_count_latest']}`",
        f"- latest Executive Context health: `{latest.get('executive_context', {}).get('system_health')}`",
        f"- latest Homeostasis status: `{latest.get('homeostasis', {}).get('status')}`",
        "",
        "## Issues",
    ]
    if summary["issues"]:
        for issue in summary["issues"]:
            lines.append(f"- `{issue['severity']}` `{issue['code']}`: `{json.dumps(issue.get('evidence'), default=str)[:700]}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Non-Core Blockers"])
    if summary["noncore_blockers"]:
        roots = sorted({item.get("root_cause") for item in summary["noncore_blockers"] if isinstance(item, dict)})
        lines.append(f"- visible non-core blockers: `{roots}`")
    else:
        lines.append("- none")
    lines.extend(["", "## PASS Criteria"])
    for key, value in summary["pass_criteria"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend([
        "",
        "## Artifacts",
        "- `memory/day3_validation_samples.jsonl`",
        "- `memory/day3_validation_summary.json`",
        "- `memory/day3_handoff.txt`",
    ])
    write_text_atomic(REPORT_PATH, "\n".join(lines) + "\n")


def recommended_next_step(summary: dict[str, Any]) -> str:
    if summary["classification"] == "INCOMPLETE":
        return "Repair or rerun the validator before using Day 3 as evidence."
    if summary["classification"] == "FAIL":
        return "Review failed core stability checks before starting Day 4."
    if summary["classification"] == "WARNING":
        return "Review Day 3 warnings and separate true core problems from non-core blockers."
    if summary["noncore_blockers"]:
        return "Keep core autonomy stable, then handle one non-core income blocker deliberately."
    return "Start Day 4 only after Andrew explicitly asks for it."


def write_handoff(summary: dict[str, Any]) -> None:
    real_failures = [issue for issue in summary["issues"] if issue["severity"] == "fail"]
    warning_issues = [issue for issue in summary["issues"] if issue["severity"] == "warning"]
    handoff = [
        f"overall result: {summary['classification']}",
        f"completed: {summary['completed']}",
        f"samples: {summary['actual_sample_count']} / expected {summary['expected_sample_count']}",
        f"elapsed_seconds: {summary['elapsed_seconds']}",
        f"completion_reason: {summary['completion_reason']}",
        f"interruption_reason: {summary.get('interruption_reason') or 'none'}",
        f"real failures: {json.dumps(real_failures, default=str) if real_failures else 'none'}",
        f"warnings: {json.dumps(warning_issues, default=str) if warning_issues else 'none'}",
        f"non-core blockers: {json.dumps(summary['noncore_blockers'], default=str) if summary['noncore_blockers'] else 'none'}",
        f"Echo Pulse healthy: {summary['pulse_healthy']}",
        f"real Experience lesson created: {bool(summary['experience_promoted_count_latest'])}",
        f"single recommended next step: {recommended_next_step(summary)}",
        "",
    ]
    write_text_atomic(HANDOFF_PATH, "\n".join(handoff))


def run_validation(duration_minutes: float, interval_minutes: float, command_used: str, once: bool = False) -> dict[str, Any]:
    start = time.monotonic()
    duration_seconds = max(0.0, duration_minutes) * 60
    end = start + duration_seconds
    interval = max(1.0, interval_minutes * 60)
    expected_count = expected_sample_count(duration_minutes, interval_minutes, once=once)
    samples: list[dict[str, Any]] = []
    index = 0
    completed = False
    completion_reason = "not_started"
    interruption_reason = None
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    try:
        while True:
            sample = collect_sample(index, start)
            append_sample(sample)
            samples.append(sample)
            index += 1
            elapsed = time.monotonic() - start
            if once:
                completed = True
                completion_reason = "once"
                break
            if elapsed >= duration_seconds and len(samples) >= expected_count:
                completed = True
                completion_reason = "duration_elapsed"
                break
            next_at = start + index * interval
            sleep_for = max(0.0, min(next_at - time.monotonic(), end - time.monotonic()))
            if sleep_for <= 0:
                continue
            time.sleep(sleep_for)
    except InterruptedRun as exc:
        completion_reason = "interrupted"
        interruption_reason = str(exc)
    except Exception as exc:
        completion_reason = "exception"
        interruption_reason = str(exc)
    elapsed_seconds = time.monotonic() - start
    run_meta = {
        "expected_sample_count": expected_count,
        "start_monotonic": start,
        "elapsed_seconds": elapsed_seconds,
        "duration_seconds": duration_seconds,
        "completion_reason": completion_reason,
        "interruption_reason": interruption_reason,
        "service_exit_status": None,
    }
    summary = analyze(samples, command_used=command_used, completed=completed, run_meta=run_meta)
    write_json_atomic(SUMMARY_PATH, summary)
    write_report(summary, samples)
    write_handoff(summary)
    return summary


def recalculate_from_samples(duration_minutes: float, interval_minutes: float, command_used: str) -> dict[str, Any]:
    runs = load_sample_runs()
    expected_count = expected_sample_count(duration_minutes, interval_minutes, once=False)
    duration_seconds = duration_minutes * 60
    samples = select_sample_run(runs, expected_count, duration_seconds)
    elapsed_seconds = sample_run_elapsed_seconds(samples)
    completed = bool(samples and len(samples) >= expected_count and elapsed_seconds >= duration_seconds)
    summary = analyze(
        samples,
        command_used=command_used,
        completed=completed,
        run_meta={
            "expected_sample_count": expected_count,
            "start_monotonic": None,
            "elapsed_seconds": elapsed_seconds,
            "duration_seconds": duration_minutes * 60,
            "completion_reason": "recalculated_from_samples" if completed else "recalculated_incomplete",
            "interruption_reason": None,
            "service_exit_status": None,
        },
    )
    write_json_atomic(SUMMARY_PATH, summary)
    write_report(summary, samples)
    write_handoff(summary)
    return summary


def self_test() -> dict[str, Any]:
    sample = collect_sample(0, time.monotonic())
    summary = analyze(
        [sample],
        command_used="self-test",
        completed=True,
        run_meta={
            "expected_sample_count": 1,
            "elapsed_seconds": 0,
            "duration_seconds": 0,
            "completion_reason": "self_test",
        },
    )
    return {
        "ok": isinstance(summary, dict) and summary.get("classification") in {"PASS", "PASS_WITH_NONCORE_BLOCKERS", "WARNING", "FAIL", "INCOMPLETE"},
        "classification": summary.get("classification"),
        "sample_keys": sorted(sample.keys()),
        "issue_count": len(summary.get("issues", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--duration-minutes", type=float, default=180.0)
    parser.add_argument("--interval-minutes", type=float, default=10.0)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--from-samples", action="store_true")
    parser.add_argument("--command-used", default="")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
    elif args.from_samples:
        command_used = args.command_used or "recalculate existing Day 3 samples"
        result = recalculate_from_samples(
            duration_minutes=args.duration_minutes,
            interval_minutes=args.interval_minutes,
            command_used=command_used,
        )
    else:
        command_used = args.command_used or "python3 tools/day3_unattended_validation.py"
        result = run_validation(
            duration_minutes=0.0 if args.once else args.duration_minutes,
            interval_minutes=args.interval_minutes,
            command_used=command_used,
            once=args.once,
        )
    if args.print_summary:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
