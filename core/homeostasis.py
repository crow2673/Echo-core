#!/usr/bin/env python3
"""Conservative reliability coordinator for Echo."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPORT_PATH = BASE / "memory/homeostasis_report.json"
STATE_PATH = BASE / "memory/homeostasis_state.json"
LOG_ANOMALY_SIGNAL_PATH = BASE / "memory/log_anomaly_signal_report.json"
LOG_PATH = BASE / "logs/homeostasis.log"

SAFE_RESTARTABLE = {
    "echo-heartbeat.service",
    "echo-disk-monitor.service",
    "echo-ollama-watchdog.service",
    "echo-log-anomaly.service",
}

PROTECTED_PREFIXES = (
    "echo-core",
    "echo-governor",
    "echo-telegram-intake",
    "echo-trader",
    "echo-crypto-trader",
    "echo-conductor",
    "echo-claude-bus-watch",
    "echo-codex-bus-watch",
)

REPAIR_COOLDOWN_SECONDS = 900
RECENT_ANOMALY_SECONDS = 3600
ACTIONABLE_ANOMALY_WARNING_THRESHOLD = 10
TELEGRAM_TRANSIENT_ESCALATE_WINDOWS = 5
TELEGRAM_SUCCESS_STALE_SECONDS = 900
LOW_SIGNAL_ANOMALY_SOURCES = {
    "journal:gnome-shell",
    "journal:steam",
}
LOW_SIGNAL_ANOMALY_PATTERNS = (
    re.compile(r"g_object_get_qdata: assertion", re.I),
    re.compile(r"Loading weights:", re.I),
    re.compile(r"unauthenticated requests to the HF Hub", re.I),
    re.compile(r"search: .* -> 0 results", re.I),
    re.compile(r"search: .* → 0 results", re.I),
    re.compile(r"search: .* -> <NUM> results", re.I),
    re.compile(r"search: .* → <NUM> results", re.I),
    re.compile(r"\[dispatcher\] step\d pass:", re.I),
    re.compile(r"\[dispatcher\] evaluating", re.I),
    re.compile(r"notified: Dispatcher: .* APPROVED", re.I),
    re.compile(r"\[notifier\] desktop suppressed .*System Log Error", re.I),
    re.compile(r"notified: System Log Error", re.I),
    re.compile(r"Consumed <NUM> CPU time", re.I),
    re.compile(r"\[core_state_writer\] updated core_state_system\.json", re.I),
    re.compile(r"Reload requested from client PID", re.I),
    re.compile(r"Reloading(?: finished)?", re.I),
    re.compile(r"status=critical critical=<NUM> warnings=<NUM>", re.I),
    re.compile(r"status=warning critical=<NUM> warnings=<NUM>", re.I),
    re.compile(r"homeostasis status=warning findings=<NUM>", re.I),
    re.compile(r"\[train\] epoch <NUM>/<NUM> loss=<NUM>", re.I),
    re.compile(r"No device provided, using cpu", re.I),
    re.compile(r"\{'loss': '<NUM>'.*'epoch': '<NUM>'\}", re.I),
    re.compile(r"\[dispatcher\] RUN .* launching", re.I),
    re.compile(r"\[dispatcher\] .* finished in <NUM>", re.I),
    re.compile(r"semantic match:", re.I),
    re.compile(r"\] matched:", re.I),
    re.compile(r"\] result: OK", re.I),
    re.compile(r"no signal .*low volume", re.I),
    re.compile(r"no signal .*RSI", re.I),
    re.compile(r"no signal .*regime=", re.I),
    re.compile(r"ADD_CONTENT skipped \(duplicate\)", re.I),
    re.compile(r"WARNING: optional failed unit:", re.I),
    re.compile(r"\[telegram\] fetch error: The read operation timed out", re.I),
    re.compile(r"\[telegram\] fetch error: .*Temporary failure in name resolution", re.I),
    re.compile(r"\[telegram\] fetch error: .*Name or service not known", re.I),
    re.compile(r"\[telegram\] fetch error: .*Connection reset by peer", re.I),
    re.compile(r"gtk_widget_get_scale_factor: assertion", re.I),
    re.compile(r"GTK_IS_WIDGET", re.I),
)
HIGH_SIGNAL_ANOMALY_PATTERNS = (
    re.compile(r"\b(error|critical|failed|failure|exception|traceback)\b", re.I),
    re.compile(r"\b(unauthorized|forbidden|denied|missing secret|no matching distribution)\b", re.I),
)
HOMEOSTASIS_STATUS_SUMMARY_RE = re.compile(
    r"^(?:\[<TS>\]\s*)?homeostasis status=(ok|warning|critical) "
    r"findings=<NUM> actions=<NUM> dry_run=(True|False)$",
    re.I,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


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
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    tmp.rename(path)


def os_pid() -> int:
    import os
    return os.getpid()


def run_cmd(args: list[str], timeout: int = 15) -> dict:
    try:
        result = subprocess.run(
            args,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


def is_protected(unit: str) -> bool:
    return any(unit.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def load_operational_audit() -> dict:
    try:
        from tools.operational_audit import build_report, write_report

        report = build_report()
        write_report(report)
        return report
    except Exception as exc:
        return {
            "assessment": {
                "status": "critical",
                "critical": [f"operational audit failed: {exc}"],
                "warnings": [],
            },
            "error": str(exc),
        }


def finding(kind: str, severity: str, message: str, **extra) -> dict:
    payload = {
        "kind": kind,
        "severity": severity,
        "message": message,
    }
    payload.update(extra)
    return payload


def collect_findings(operational: dict) -> list[dict]:
    findings: list[dict] = []
    assessment = operational.get("assessment", {})

    for message in assessment.get("critical", []):
        if "Failed to connect to user scope bus" in message:
            findings.append(
                finding(
                    "warning",
                    "warning",
                    "systemd user bus unavailable to homeostasis check",
                )
            )
            continue
        unit = _extract_unit(message)
        if unit == "echo-offsite-backup.service" and offsite_backup_transport_deferred():
            findings.append(offsite_backup_finding())
            continue
        if unit and unit in SAFE_RESTARTABLE:
            findings.append(finding("safe_restart", "critical", message, unit=unit))
        elif unit and is_protected(unit):
            findings.append(finding("needs_andrew", "critical", message, unit=unit))
        else:
            findings.append(finding("needs_andrew", "critical", message, unit=unit))

    for message in assessment.get("warnings", []):
        unit = _extract_unit(message)
        if unit == "echo-offsite-backup.service" and offsite_backup_transport_deferred():
            findings.append(offsite_backup_finding())
            continue
        findings.append(finding("warning", "warning", message))

    core_state = load_json(BASE / "memory/core_state_system.json", {})
    for name, info in core_state.get("workers", {}).items():
        unit = info.get("service")
        if info.get("stale") and unit:
            if unit in SAFE_RESTARTABLE:
                findings.append(
                    finding(
                        "safe_restart",
                        "warning",
                        f"stale safe worker: {name} ({unit})",
                        unit=unit,
                        worker=name,
                    )
                )
            else:
                findings.append(
                    finding(
                        "needs_andrew",
                        "warning",
                        f"stale worker requires review: {name} ({unit})",
                        unit=unit,
                        worker=name,
                    )
                )

    echo_state = load_json(BASE / "memory/echo_state.json", {})
    if echo_state:
        timestamp = echo_state.get("timestamp")
        age = _age_seconds(timestamp)
        if age is not None and age > 900:
            findings.append(
                finding("needs_andrew", "critical", f"echo_state stale: {age}s old")
            )
        failed = echo_state.get("failed_units")
        if isinstance(failed, dict):
            for unit in failed.get("units", []):
                if not unit_is_failed(unit):
                    continue
                if unit == "echo-offsite-backup.service" and offsite_backup_transport_deferred():
                    findings.append(offsite_backup_finding())
                    continue
                if unit in SAFE_RESTARTABLE:
                    findings.append(finding("safe_restart", "critical", f"failed unit: {unit}", unit=unit))
                else:
                    findings.append(finding("needs_andrew", "critical", f"failed unit: {unit}", unit=unit))

    if importlib.util.find_spec("sentence_transformers") is None:
        findings.append(
            finding(
                "needs_andrew",
                "critical",
                "semantic memory dependency missing: sentence_transformers",
            )
        )

    findings.extend(_recent_semantic_failures())
    findings.extend(_recent_log_anomalies())
    if offsite_backup_transport_deferred():
        findings.append(offsite_backup_finding())
    return _dedupe_findings(findings)


def load_offsite_backup_status() -> dict:
    return load_json(BASE / "memory/offsite_backup_status.json", {})


def offsite_backup_transport_deferred() -> bool:
    status = load_offsite_backup_status()
    artifact = status.get("artifact_path")
    return bool(
        status.get("local_backup_created")
        and status.get("encryption_completed")
        and status.get("offsite_delivery_pending")
        and artifact
        and (BASE / artifact).exists()
    )


def offsite_backup_delivery_escalated(status: dict | None = None) -> bool:
    status = status or load_offsite_backup_status()
    attempts = int(status.get("delivery_attempts") or 0)
    max_attempts = int(status.get("max_delivery_attempts") or 3)
    created = _age_seconds(status.get("updated_at"))
    return attempts >= max_attempts or (created is not None and created > 36 * 60 * 60)


def offsite_backup_finding() -> dict:
    status = load_offsite_backup_status()
    severity = "warning" if offsite_backup_delivery_escalated(status) else "info"
    return {
        "kind": "backup_delivery",
        "severity": severity,
        "classification": "capability_blocker",
        "domain": "backup",
        "message": "offsite backup delivery pending; encrypted local artifact preserved",
        "unit": "echo-offsite-backup.service",
        "artifact_path": status.get("artifact_path"),
        "delivery_attempts": status.get("delivery_attempts", 0),
        "next_retry_at": status.get("next_retry_at"),
        "last_error": status.get("last_error"),
    }


def _extract_unit(message: str) -> str | None:
    for token in str(message).replace("=", " ").replace(":", " ").split():
        if token.endswith((".service", ".timer")) and token.startswith(("echo-", "crow-")):
            return token
    return None


def _age_seconds(timestamp: str | None) -> int | None:
    if not timestamp:
        return None
    try:
        raw = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return int((utcnow() - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _recent_semantic_failures() -> list[dict]:
    path = BASE / "logs/telegram_intake.log"
    if not path.exists():
        return []
    try:
        lines = path.read_text(errors="replace").splitlines()[-200:]
    except Exception:
        return []
    recent = [line for line in lines if "semantic recall failed" in line or "semantic store failed" in line]
    if recent:
        return [
            finding(
                "needs_andrew",
                "warning",
                f"recent semantic memory failures in telegram_intake.log: {len(recent)}",
            )
        ]
    return []


def _recent_log_anomalies() -> list[dict]:
    data = load_json(BASE / "memory/log_anomaly_findings.json", {})
    vocab = load_json(BASE / "memory/log_key_vocab.json", {})
    templates = vocab.get("templates", {}) if isinstance(vocab, dict) else {}
    recent = []
    for item in data.get("findings", []):
        detected = item.get("detected_at")
        age = _age_seconds(detected)
        if age is not None and age <= RECENT_ANOMALY_SECONDS:
            recent.append(item)
    if not recent:
        write_json(LOG_ANOMALY_SIGNAL_PATH, {
            "updated_at": iso_now(),
            "recent_count": 0,
            "actionable_count": 0,
            "suppressed_low_signal_count": 0,
        })
        return []

    actionable = []
    suppressed = []
    for item in recent:
        template = _anomaly_template(item, templates)
        enriched = {**item, "template": template}
        if _is_low_signal_anomaly(enriched):
            suppressed.append(enriched)
        elif _is_high_signal_anomaly(enriched):
            actionable.append(enriched)
        else:
            suppressed.append(enriched)

    source_counts = Counter(item.get("source", "unknown") for item in recent)
    raw_actionable_sources = Counter(item.get("source", "unknown") for item in actionable)
    suppressed_sources = Counter(item.get("source", "unknown") for item in suppressed)
    incidents = _group_anomaly_incidents(actionable)
    core_operational = [item for item in incidents if item.get("classification") == "core_operational" and item.get("active")]
    capability_blockers = [item for item in incidents if item.get("classification") == "capability_blocker" and item.get("active")]
    transient_incidents = [item for item in incidents if item.get("classification") == "transient"]
    maintenance_incidents = [item for item in incidents if item.get("classification") == "maintenance"]
    resolved_historical = [item for item in incidents if item.get("classification") == "resolved_historical"]
    incident_sources = Counter(item.get("source", "unknown") for item in incidents)
    write_json(LOG_ANOMALY_SIGNAL_PATH, {
        "updated_at": iso_now(),
        "recent_count": len(recent),
        "actionable_count": len(actionable),
        "raw_window_count": len(actionable),
        "unique_incident_count": len(incidents),
        "active_core_operational_count": len(core_operational),
        "active_capability_blocker_count": len(capability_blockers),
        "transient_incident_count": len(transient_incidents),
        "maintenance_incident_count": len(maintenance_incidents),
        "resolved_historical_count": len(resolved_historical),
        "suppressed_low_signal_count": len(suppressed),
        "top_recent_sources": dict(source_counts.most_common(8)),
        "top_actionable_sources": dict(raw_actionable_sources.most_common(8)),
        "top_incident_sources": dict(incident_sources.most_common(8)),
        "top_suppressed_sources": dict(suppressed_sources.most_common(8)),
        "core_operational_incidents": core_operational[:20],
        "capability_blockers": capability_blockers[:20],
        "transient_incidents": transient_incidents[:20],
        "maintenance_incidents": maintenance_incidents[:20],
        "resolved_historical": resolved_historical[:20],
        "sample_actionable": [
            {
                "source": item.get("source"),
                "target_key": item.get("target_key"),
                "template": item.get("template", "")[:240],
            }
            for item in actionable[:10]
        ],
    })
    if not core_operational:
        return []

    raw_windows = sum(int(item.get("raw_window_count", 0) or 0) for item in core_operational)
    top = ", ".join(
        f"{src} x{count}" for src, count in Counter(item.get("source", "unknown") for item in core_operational).most_common(3)
    )
    return [
        finding(
            "warning",
            "warning",
            f"active core log anomaly incidents: {len(core_operational)} unique, {raw_windows} raw windows ({top})",
            classification="core_operational",
            domain="core",
            unique_incident_count=len(core_operational),
            raw_window_count=raw_windows,
            suppressed_low_signal=len(suppressed),
            incidents=core_operational[:10],
        )
    ]


def _group_anomaly_incidents(actionable: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in actionable:
        key = (str(item.get("source") or "unknown"), str(item.get("target_key") or "unknown"))
        grouped.setdefault(key, []).append(item)

    incidents = []
    for (source, target_key), windows in sorted(grouped.items()):
        template = str(windows[0].get("template") or "")
        source_timestamps = sorted(
            str(item.get("source_ts") or item.get("ts") or item.get("timestamp") or "")
            for item in windows
            if item.get("source_ts") or item.get("ts") or item.get("timestamp")
        )
        scan_timestamps = sorted(
            str(item.get("detected_at") or "")
            for item in windows
            if item.get("detected_at")
        )
        first_source_seen = source_timestamps[0] if source_timestamps else (scan_timestamps[0] if scan_timestamps else "")
        last_source_seen = source_timestamps[-1] if source_timestamps else (scan_timestamps[-1] if scan_timestamps else "")
        incident = _classify_anomaly_incident(
            source=source,
            target_key=target_key,
            template=template,
            raw_window_count=len(windows),
            first_seen=first_source_seen,
            last_seen=last_source_seen,
        )
        incident.update({
            "source": source,
            "target_key": target_key,
            "template": template[:300],
            "raw_window_count": len(windows),
            "first_seen": first_source_seen,
            "last_seen": last_source_seen,
            "source_first_seen": first_source_seen,
            "source_last_seen": last_source_seen,
            "scan_first_seen": scan_timestamps[0] if scan_timestamps else "",
            "scan_last_seen": scan_timestamps[-1] if scan_timestamps else "",
        })
        incidents.append(incident)
    _record_incident_lifecycle_events(incidents)
    return incidents


def _record_incident_lifecycle_events(incidents: list[dict]) -> None:
    if not incidents:
        return
    state = load_json(STATE_PATH, {"last_repair_by_unit": {}})
    events = list(state.get("incident_lifecycle_events", []))
    seen = {str(event.get("event_fingerprint")) for event in events if event.get("event_fingerprint")}
    changed = False
    for incident in incidents:
        payload = {
            "source": incident.get("source"),
            "target_key": incident.get("target_key"),
            "classification": incident.get("classification"),
            "active": bool(incident.get("active")),
            "lifecycle_state": incident.get("lifecycle_state"),
            "source_first_seen": incident.get("source_first_seen") or incident.get("first_seen"),
            "source_last_seen": incident.get("source_last_seen") or incident.get("last_seen"),
            "scan_first_seen": incident.get("scan_first_seen"),
            "scan_last_seen": incident.get("scan_last_seen"),
        }
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if fingerprint in seen:
            continue
        events.append({
            "event_fingerprint": fingerprint,
            "recorded_at": iso_now(),
            **payload,
        })
        seen.add(fingerprint)
        changed = True
    if changed:
        state["incident_lifecycle_events"] = events[-500:]
        write_json(STATE_PATH, state)


def _classify_anomaly_incident(
    source: str,
    target_key: str,
    template: str,
    raw_window_count: int = 1,
    first_seen: str | None = None,
    last_seen: str | None = None,
) -> dict:
    text = f"{source} {template}"
    lowered = text.lower()

    if _is_homeostasis_status_summary(source, template):
        return {
            "classification": "maintenance",
            "domain": "observability",
            "active": False,
            "root_cause": "homeostasis_generated_status_summary",
            "lifecycle_state": "excluded_self_reference",
            "producer": "homeostasis",
            "evidence_role": "generated_status_summary",
            "message": (
                "Homeostasis status summary is generated classifier output, "
                "not independent operational failure evidence."
            ),
        }

    if source == "file:system_health.log" and "failed to start" in lowered:
        unit = _extract_unit(template)
        active = bool(unit and unit_is_failed(unit))
        return {
            "classification": "core_operational" if active else "resolved_historical",
            "domain": "core",
            "active": active,
            "unit": unit,
            "root_cause": "current_failed_unit" if active else "historical_failed_unit_log",
            "message": (
                f"current failed unit in system_health.log: {unit}"
                if active else f"historical failed-unit log no longer active: {unit or 'unknown unit'}"
            ),
        }

    if source == "file:income.log" and "vast" in lowered and ("cli error" in lowered or "modulenotfounderror" in lowered):
        return {
            "classification": "capability_blocker",
            "domain": "income",
            "active": True,
            "root_cause": "vast_monitor_missing_vast_package",
            "message": "Vast monitor cannot run because the vast Python module is missing.",
        }

    if source in {"file:fiverr_fulfiller.log", "file:fiverr_inbox.log"} and (
        "login failed" in lowered or "continue with google" in lowered
    ):
        root = "fiverr_fulfiller_login_failed" if source == "file:fiverr_fulfiller.log" else "fiverr_inbox_login_failed"
        return {
            "classification": "capability_blocker",
            "domain": "income",
            "active": True,
            "root_cause": root,
            "message": "Fiverr automation cannot log in through the current Google SSO flow.",
        }

    if source == "file:outcome_loop.log" and template.startswith("outcome_loop succeeded="):
        return {
            "classification": "maintenance",
            "domain": "observability",
            "active": False,
            "root_cause": "outcome_loop_summary_contains_failed_counter",
            "message": "Outcome loop summary line matched failure keyword but is not itself a failure.",
        }

    if source == "file:life_loop.log" and "restore system health" in lowered:
        if unit_is_failed("echo-life-loop.service"):
            return {
                "classification": "core_operational",
                "domain": "core",
                "active": True,
                "unit": "echo-life-loop.service",
                "root_cause": "life_loop_service_failed",
                "message": "Life Loop service is currently failed.",
            }
        return {
            "classification": "resolved_historical",
            "domain": "core",
            "active": False,
            "root_cause": "life_loop_status_echo",
            "message": "Life Loop restore-health status text is historical/self-reported and not a current core incident.",
            "current_health": _current_executive_health(),
            "current_life_priority": _current_life_priority_title(),
        }

    if source == "file:briefing.log" and "[router] call_ollama error" in lowered:
        service_failed = unit_is_failed("echo-daily-briefing.service")
        success_after = briefing_success_after(last_seen)
        if service_failed:
            return {
                "classification": "core_operational",
                "domain": "core",
                "active": True,
                "unit": "echo-daily-briefing.service",
                "root_cause": "daily_briefing_service_failed",
                "message": "Daily briefing service is currently failed.",
                "success_after_incident": success_after,
            }
        if success_after:
            return {
                "classification": "transient",
                "domain": "communication",
                "active": False,
                "root_cause": "briefing_ollama_warmup_timeout_resolved",
                "message": "Daily briefing Ollama warmup timed out, but a later briefing generated successfully.",
                "success_after_incident": True,
            }
        return {
            "classification": "capability_blocker",
            "domain": "communication",
            "active": True,
            "root_cause": "daily_briefing_ollama_generation_blocked",
            "message": "Daily briefing could not confirm a successful generation after the Ollama call error.",
            "success_after_incident": False,
        }

    if source == "file:telegram_intake.log":
        if _telegram_auth_or_config_failure(lowered):
            return {
                "classification": "capability_blocker",
                "domain": "communication",
                "active": True,
                "root_cause": "telegram_auth_or_config_failure",
                "message": "Telegram intake has an authentication or configuration failure.",
            }
        if _telegram_transient_error(lowered):
            service_failed = unit_is_failed("echo-telegram-intake.service")
            timer_active = unit_is_active("echo-telegram-intake.timer")
            success_after = telegram_success_after(last_seen)
            if service_failed or not timer_active:
                return {
                    "classification": "core_operational",
                    "domain": "core",
                    "active": True,
                    "unit": "echo-telegram-intake.service" if service_failed else "echo-telegram-intake.timer",
                    "root_cause": "telegram_intake_service_or_timer_unhealthy",
                    "message": "Telegram intake transient errors coincide with an unhealthy service or timer.",
                    "raw_window_count": raw_window_count,
                    "success_after_incident": success_after,
                }
            if raw_window_count >= TELEGRAM_TRANSIENT_ESCALATE_WINDOWS and not success_after:
                return {
                    "classification": "capability_blocker",
                    "domain": "communication",
                    "active": True,
                    "root_cause": "telegram_recurring_degraded_condition",
                    "message": "Telegram intake transient polling errors have persisted without later successful polling.",
                    "raw_window_count": raw_window_count,
                    "threshold": TELEGRAM_TRANSIENT_ESCALATE_WINDOWS,
                    "success_after_incident": success_after,
                    "lifecycle_state": "recurring_degraded",
                }
            return {
                "classification": "transient",
                "domain": "communication",
                "active": not success_after,
                "root_cause": "telegram_recoverable_polling_error",
                "message": (
                    "Telegram intake recoverable polling/network error resolved by later success."
                    if success_after else "Telegram intake recoverable polling/network error below persistence threshold."
                ),
                "raw_window_count": raw_window_count,
                "threshold": TELEGRAM_TRANSIENT_ESCALATE_WINDOWS,
                "success_after_incident": success_after,
                "lifecycle_state": "recovered_transient" if success_after else "active_transient",
            }

    return {
        "classification": "core_operational",
        "domain": "core",
        "active": True,
        "root_cause": "unclassified_high_signal_log_anomaly",
        "message": "Unclassified high-signal log anomaly requires review.",
    }


def _current_executive_health() -> str:
    return str(load_json(BASE / "memory/executive_context.json", {}).get("system_health") or "unknown")


def _current_life_priority_title() -> str:
    state = load_json(BASE / "memory/life_loop_state.json", {})
    priority = state.get("current_priority", {}) if isinstance(state, dict) else {}
    return str(priority.get("title") or "")


def unit_is_active(unit: str) -> bool:
    result = run_cmd(["systemctl", "--user", "is-active", unit], timeout=10)
    return result.get("stdout", "").strip() == "active"


def _telegram_auth_or_config_failure(text: str) -> bool:
    return any(
        token in text
        for token in (
            "unauthorized",
            "forbidden",
            "invalid token",
            "401",
            "403",
            "no token configured",
            "chat not found",
        )
    )


def _telegram_transient_error(text: str) -> bool:
    return any(
        token in text
        for token in (
            "too many requests",
            "429",
            "502",
            "bad gateway",
            "timed out",
            "timeout",
            "connection reset",
            "temporary failure",
            "network is unreachable",
            "name or service not known",
            "handshake operation timed out",
        )
    )


def telegram_success_after(timestamp: str | None, log_path: Path | None = None) -> bool:
    path = log_path or (BASE / "logs/telegram_intake.log")
    if not path.exists():
        return False
    threshold = _parse_timestamp(timestamp)
    try:
        lines = path.read_text(errors="replace").splitlines()[-500:]
    except Exception:
        return False
    for line in lines:
        ts = _parse_log_line_timestamp(line)
        if threshold and ts and ts <= threshold:
            continue
        if not threshold and ts:
            age = int((utcnow() - ts.astimezone(timezone.utc)).total_seconds())
            if age > TELEGRAM_SUCCESS_STALE_SECONDS:
                continue
        if _is_telegram_success_line(line):
            return True
    return False


def briefing_success_after(timestamp: str | None, log_path: Path | None = None) -> bool:
    path = log_path or (BASE / "logs/briefing.log")
    if not path.exists():
        return False
    threshold = _parse_timestamp(timestamp)
    try:
        lines = path.read_text(errors="replace").splitlines()[-500:]
    except Exception:
        return False
    seen_threshold = threshold is None
    for line in lines:
        ts = _parse_log_line_timestamp(line)
        if threshold and ts:
            seen_threshold = ts > threshold
        elif threshold and "[router] call_ollama error" in line:
            seen_threshold = True
        if not seen_threshold:
            continue
        if "[briefing] Generated:" in line or "[briefing] Spoken successfully" in line:
            return True
    return False


def _is_telegram_success_line(line: str) -> bool:
    return any(
        token in line
        for token in (
            "[telegram] from ",
            "[telegram] shift report sent",
            "[telegram] command ",
            "[telegram] build ready:",
            "handled as pending content approval",
        )
    )


def _parse_log_line_timestamp(line: str) -> datetime | None:
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}", line)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
        except Exception:
            return None
    match = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
        except Exception:
            return None
    return None


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        raw = timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed
    except Exception:
        return None


def _anomaly_template(item: dict, templates: dict) -> str:
    target_key = item.get("target_key")
    template = ""
    if target_key and isinstance(templates.get(target_key), dict):
        template = str(templates[target_key].get("template") or "")
    return template


def _is_low_signal_anomaly(item: dict) -> bool:
    source = item.get("source", "")
    template = item.get("template", "")
    if source in LOW_SIGNAL_ANOMALY_SOURCES:
        return True
    if _is_homeostasis_status_summary(source, template):
        return False
    return any(pattern.search(template) for pattern in LOW_SIGNAL_ANOMALY_PATTERNS)


def _is_high_signal_anomaly(item: dict) -> bool:
    template = item.get("template", "")
    source = item.get("source", "")
    if _is_homeostasis_status_summary(source, template):
        return True
    return any(pattern.search(template) for pattern in HIGH_SIGNAL_ANOMALY_PATTERNS)


def _is_homeostasis_status_summary(source: str, template: str) -> bool:
    return source == "file:homeostasis.log" and bool(HOMEOSTASIS_STATUS_SUMMARY_RE.match(str(template).strip()))


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in findings:
        key = (item.get("kind"), item.get("severity"), item.get("message"), item.get("unit"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def restart_unit(unit: str) -> dict:
    if unit not in SAFE_RESTARTABLE:
        return {"unit": unit, "action": "refused", "reason": "not in safe restart allowlist"}
    result = run_cmd(["systemctl", "--user", "restart", unit], timeout=20)
    action = "restarted" if result["ok"] else "restart_failed"
    return {
        "unit": unit,
        "action": action,
        "returncode": result["returncode"],
        "stderr": result["stderr"],
    }


def unit_is_failed(unit: str) -> bool:
    result = run_cmd(["systemctl", "--user", "is-failed", unit], timeout=10)
    return result.get("stdout", "").strip() == "failed"


def apply_repairs(findings: list[dict], state: dict, dry_run: bool) -> list[dict]:
    actions = []
    last = state.setdefault("last_repair_by_unit", {})
    now = utcnow()
    for item in findings:
        if item.get("kind") != "safe_restart":
            continue
        unit = item.get("unit")
        if not unit:
            continue
        prior = last.get(unit)
        if prior and _age_seconds(prior) is not None and _age_seconds(prior) < REPAIR_COOLDOWN_SECONDS:
            actions.append({"unit": unit, "action": "cooldown", "reason": item["message"]})
            continue
        if dry_run:
            actions.append({"unit": unit, "action": "would_restart", "reason": item["message"]})
            continue
        result = restart_unit(unit)
        result["reason"] = item["message"]
        actions.append(result)
        last[unit] = now.isoformat()
        log(f"{result['action']} {unit}: {item['message']}")
    return actions


def report_status(findings: list[dict]) -> str:
    operational = [
        item for item in findings
        if item.get("classification") not in {"capability_blocker", "maintenance", "resolved_historical", "transient"}
    ]
    if any(item.get("severity") == "critical" for item in operational):
        return "critical"
    if operational:
        return "warning"
    return "ok"


def operational_system_health(report: dict) -> str:
    """Return core operational health for Executive Context.

    The report status may be warning because of review items, capability
    blockers, or maintenance. Executive Context system_health is narrower: it
    should reflect active core operational impairment.
    """
    findings = report.get("findings", [])
    operational = [
        item for item in findings
        if item.get("classification") not in {"capability_blocker", "maintenance", "resolved_historical", "transient"}
    ]
    if any(item.get("severity") == "critical" for item in operational):
        return "critical"
    anomaly_summary = report.get("anomaly_summary", {})
    if int(anomaly_summary.get("active_core_operational_count", 0) or 0) > 0:
        return "warning"
    if any(item.get("classification") == "core_operational" and item.get("severity") == "warning" for item in operational):
        return "warning"
    return "OK"


def sync_operational_health(report: dict) -> None:
    system_health = operational_system_health(report)
    try:
        from core.executive_context import safe_update

        safe_update(
            {
                "system_health": system_health,
                "capability_blockers": report.get("capability_blockers", []),
                "maintenance_findings": report.get("maintenance_findings", []),
            },
            source="homeostasis",
            reason="homeostasis owns operational system health",
        )
    except Exception as exc:
        log(f"executive_context health sync failed: {exc}")


def fingerprint_findings(findings: list[dict]) -> str:
    stable = [
        {
            "kind": item.get("kind"),
            "severity": item.get("severity"),
            "message": item.get("message"),
            "unit": item.get("unit"),
        }
        for item in findings
        if item.get("severity") == "critical" or item.get("kind") == "needs_andrew"
    ]
    raw = json.dumps(stable, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def maybe_notify(report: dict, state: dict, dry_run: bool, no_notify: bool) -> None:
    if dry_run or no_notify or report["status"] == "ok":
        return
    fingerprint = fingerprint_findings(report["findings"])
    if fingerprint == state.get("last_notified_fingerprint"):
        return
    critical = [f for f in report["findings"] if f.get("severity") == "critical"]
    needs = [f for f in report["findings"] if f.get("kind") == "needs_andrew"]
    if not critical and not needs:
        return
    summary = critical[0]["message"] if critical else needs[0]["message"]
    try:
        from core.notifier import notify

        notify(
            "Echo Homeostasis",
            f"{report['status']}: {summary}",
            urgent=bool(critical),
            phone=True,
        )
        state["last_notified_fingerprint"] = fingerprint
        state["last_notified_at"] = iso_now()
    except Exception as exc:
        log(f"notify failed: {exc}")


def run(dry_run: bool = False, notify: bool = True) -> dict:
    state = load_json(STATE_PATH, {"last_repair_by_unit": {}})
    operational = load_operational_audit()
    findings = collect_findings(operational)
    refreshed_state = load_json(STATE_PATH, {"last_repair_by_unit": {}})
    if refreshed_state.get("incident_lifecycle_events"):
        state["incident_lifecycle_events"] = refreshed_state.get("incident_lifecycle_events", [])
    actions = apply_repairs(findings, state, dry_run=dry_run)
    anomaly_signal = load_json(LOG_ANOMALY_SIGNAL_PATH, {})
    capability_blockers = list(anomaly_signal.get("capability_blockers", []))
    transient_findings = list(anomaly_signal.get("transient_incidents", []))
    capability_blockers.extend(
        item for item in findings
        if item.get("classification") == "capability_blocker" and item.get("active", True)
    )
    maintenance_findings = list(operational.get("assessment", {}).get("maintenance", []))
    maintenance_findings.extend(
        item.get("message", "maintenance anomaly")
        for item in anomaly_signal.get("maintenance_incidents", [])
    )
    report = {
        "updated_at": iso_now(),
        "status": report_status(findings),
        "dry_run": dry_run,
        "findings": findings,
        "actions_taken": actions,
        "needs_andrew": [item for item in findings if item.get("kind") == "needs_andrew"],
        "capability_blockers": capability_blockers,
        "transient_findings": transient_findings,
        "maintenance_findings": maintenance_findings,
        "resolved_historical": anomaly_signal.get("resolved_historical", []),
        "anomaly_summary": {
            "raw_window_count": anomaly_signal.get("raw_window_count", 0),
            "unique_incident_count": anomaly_signal.get("unique_incident_count", 0),
            "active_core_operational_count": anomaly_signal.get("active_core_operational_count", 0),
            "active_capability_blocker_count": anomaly_signal.get("active_capability_blocker_count", 0),
            "transient_incident_count": anomaly_signal.get("transient_incident_count", 0),
            "resolved_historical_count": anomaly_signal.get("resolved_historical_count", 0),
        },
        "sources": {
            "operational_audit": str(BASE / "memory/operational_audit.json"),
            "core_state": str(BASE / "memory/core_state_system.json"),
            "echo_state": str(BASE / "memory/echo_state.json"),
        },
    }
    if not dry_run:
        sync_operational_health(report)
    maybe_notify(report, state, dry_run=dry_run, no_notify=not notify)
    if not dry_run:
        write_json(STATE_PATH, state)
    write_json(REPORT_PATH, report)
    log(
        f"homeostasis status={report['status']} findings={len(findings)} "
        f"actions={len(actions)} dry_run={dry_run}"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    report = run(dry_run=args.dry_run, notify=not args.no_notify)
    if args.print:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
