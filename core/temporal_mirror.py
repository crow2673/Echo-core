#!/usr/bin/env python3
"""
core/temporal_mirror.py — Causal link discovery for Echo's memory.

Reads recent events from decision_trace.jsonl and the builds/gaps/goals
record, then finds structural pairs: a failure/gap event followed by a
resolution/build/success event on the same topic.

Writes provisional causal links to memory/causal_links.jsonl.
Links are two-phase:
  provisional  — found by structural matching, confidence < 1.0
  confirmed    — corroborated by a later event or N independent matches
  expired      — provisional, unconfirmed after 14 days (pruned)

This is the Observer's Tax-aware version: no LLM calls, no added latency.
Pure structural/temporal matching. Runs daily overnight.

The causal_links.jsonl file is read by _build_grounded_context in self_act
so Echo can see "this gap was closed by this build" in her reasoning context.
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DECISION_TRACE = BASE / "memory" / "decision_trace.jsonl"
CAUSAL_LINKS = BASE / "memory" / "causal_links.jsonl"
GAP_INDEX = BASE / "memory" / "gap_index.json"
BUILD_REGISTRY = BASE / "builds" / "registry.json"
GOALS_FILE = BASE / "memory" / "persistent_goals.json"
LOG = BASE / "logs" / "temporal_mirror.log"
LOG.parent.mkdir(exist_ok=True)

PROVISIONAL_EXPIRY_DAYS = 14
MAX_LINKS = 500         # cap causal_links.jsonl size


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [temporal_mirror] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


STOPWORDS = {
    "the", "and", "for", "this", "that", "with", "from", "into", "will",
    "have", "been", "echo", "make", "using", "which", "when", "then", "also",
    "failed", "error", "success", "result", "found", "check", "read", "file",
}


def _keywords(text: str) -> set:
    words = re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split()
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def _overlap_score(a: str, b: str) -> float:
    ka, kb = _keywords(a), _keywords(b)
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / max(len(ka | kb), 1)


def _is_failure_signal(entry: dict) -> bool:
    text = " ".join(str(v) for v in entry.values()).lower()
    signals = ["failed", "error", "gap", "missing", "broken", "blocked",
               "timeout", "not found", "needs_andrew", "exception", "traceback"]
    return any(s in text for s in signals)


def _is_resolution_signal(entry: dict) -> bool:
    text = " ".join(str(v) for v in entry.values()).lower()
    signals = ["deployed", "resolved", "fixed", "success", "completed",
               "approved", "solved", "integrated", "active", "working"]
    return any(s in text for s in signals)


def _load_trace_entries(max_entries: int = 1000) -> list:
    if not DECISION_TRACE.exists():
        return []
    entries = []
    for line in DECISION_TRACE.read_text().splitlines()[-max_entries:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries


def _load_existing_links() -> list:
    if not CAUSAL_LINKS.exists():
        return []
    links = []
    for line in CAUSAL_LINKS.read_text().splitlines():
        try:
            links.append(json.loads(line))
        except Exception:
            pass
    return links


def _save_links(links: list):
    # Keep only newest MAX_LINKS
    links = links[-MAX_LINKS:]
    with open(CAUSAL_LINKS, "w") as f:
        for link in links:
            f.write(json.dumps(link) + "\n")


def _find_trace_pairs(entries: list) -> list:
    """
    Find (failure_entry, resolution_entry) pairs in the decision trace.
    Look-forward window: resolution must occur within 7 days of failure.
    Minimum overlap score: 0.25 on topic keywords.
    """
    pairs = []
    window = timedelta(days=7)

    failure_entries = [(i, e) for i, e in enumerate(entries) if _is_failure_signal(e)]
    resolution_entries = [(i, e) for i, e in enumerate(entries) if _is_resolution_signal(e)]

    for fi, fe in failure_entries:
        f_ts_str = fe.get("timestamp") or fe.get("ts", "")
        try:
            f_ts = datetime.fromisoformat(f_ts_str)
        except Exception:
            continue

        f_text = " ".join(str(v) for v in fe.values())

        for ri, re_entry in resolution_entries:
            if ri <= fi:
                continue  # resolution must come AFTER failure
            r_ts_str = re_entry.get("timestamp") or re_entry.get("ts", "")
            try:
                r_ts = datetime.fromisoformat(r_ts_str)
            except Exception:
                continue
            if r_ts - f_ts > window:
                break  # entries are chronological; no need to look further

            r_text = " ".join(str(v) for v in re_entry.values())
            score = _overlap_score(f_text, r_text)
            if score >= 0.25:
                pairs.append((fe, re_entry, score))

    return pairs


def _find_gap_build_pairs() -> list:
    """
    Match gaps in gap_index.json to builds in builds/registry.json by keyword overlap.
    Returns pairs (gap, build_name, score).
    """
    pairs = []
    if not GAP_INDEX.exists() or not BUILD_REGISTRY.exists():
        return pairs

    try:
        gaps = json.loads(GAP_INDEX.read_text()).get("gaps", {})
        builds = json.loads(BUILD_REGISTRY.read_text())
    except Exception:
        return pairs

    for gap_id, gap in gaps.items():
        if gap.get("status") in ("resolved",):
            continue
        gap_text = gap.get("text", "")
        for build_name, build in builds.items():
            if build.get("status") not in ("deployed",):
                continue
            build_text = build.get("description", "") + " " + build_name
            score = _overlap_score(gap_text, build_text)
            if score >= 0.30:
                pairs.append((gap, build_name, build, score))

    return pairs


def _find_goal_resolution_pairs() -> list:
    """Find goals that moved to 'solved' and link them to their linked gap."""
    if not GOALS_FILE.exists():
        return []
    try:
        goals = json.loads(GOALS_FILE.read_text()).get("goals", [])
    except Exception:
        return []

    pairs = []
    for g in goals:
        if g.get("status") == "solved" and g.get("gap_id") and g.get("solution_evidence"):
            pairs.append(g)
    return pairs


def run():
    log("starting")
    existing_links = _load_existing_links()
    existing_link_ids = {l.get("link_id") for l in existing_links}

    now = datetime.now()
    new_links = []
    updated_links = []

    # Expire old provisional links
    kept_links = []
    expired = 0
    for link in existing_links:
        if link.get("status") == "provisional":
            created = link.get("created_at", "")
            try:
                age = (now - datetime.fromisoformat(created)).days
                if age > PROVISIONAL_EXPIRY_DAYS:
                    expired += 1
                    continue
            except Exception:
                pass
        kept_links.append(link)
    if expired:
        log(f"expired {expired} unconfirmed provisional links")

    # 1. Decision trace pairs
    entries = _load_trace_entries(max_entries=500)
    if entries:
        pairs = _find_trace_pairs(entries)
        log(f"decision trace: {len(entries)} entries → {len(pairs)} candidate pairs")
        for failure, resolution, score in pairs:
            # Stable ID based on content hash
            import hashlib
            content = (str(failure) + str(resolution))[:200]
            link_id = "tl_" + hashlib.md5(content.encode()).hexdigest()[:12]
            if link_id in existing_link_ids:
                continue
            new_links.append({
                "link_id": link_id,
                "type": "trace_pair",
                "status": "provisional",
                "confidence": round(score, 3),
                "failure": {
                    "ts": failure.get("timestamp") or failure.get("ts", ""),
                    "summary": str(failure.get("result", failure.get("action", "")))[:150],
                },
                "resolution": {
                    "ts": resolution.get("timestamp") or resolution.get("ts", ""),
                    "summary": str(resolution.get("result", resolution.get("action", "")))[:150],
                },
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(days=PROVISIONAL_EXPIRY_DAYS)).isoformat(),
            })

    # 2. Gap → Build pairs
    gap_build_pairs = _find_gap_build_pairs()
    log(f"gap-build: {len(gap_build_pairs)} candidate pairs")
    for gap, build_name, build, score in gap_build_pairs:
        import hashlib
        link_id = "gb_" + hashlib.md5((gap["id"] + build_name).encode()).hexdigest()[:12]
        if link_id in existing_link_ids:
            continue
        verified = bool(build.get("verification_evidence") or build.get("verified_outcome"))
        new_links.append({
            "link_id": link_id,
            "type": "gap_build",
            "status": "confirmed" if verified else "provisional",
            "confidence": round(score, 3),
            "gap_id": gap["id"],
            "gap_text": gap["text"][:120],
            "build_name": build_name,
            "build_description": build.get("description", "")[:120],
            "verification_evidence": build.get("verification_evidence", ""),
            "created_at": now.isoformat(),
        })

    # 3. Goal resolution pairs
    resolved_goals = _find_goal_resolution_pairs()
    log(f"goal resolutions: {len(resolved_goals)} solved goals with linked gaps")
    for goal in resolved_goals:
        import hashlib
        link_id = "gr_" + hashlib.md5((goal["id"] + str(goal.get("gap_id", ""))).encode()).hexdigest()[:12]
        if link_id in existing_link_ids:
            continue
        new_links.append({
            "link_id": link_id,
            "type": "goal_resolution",
            "status": "confirmed",
            "confidence": 1.0,
            "goal_id": goal["id"],
            "gap_id": goal.get("gap_id"),
            "description": goal.get("description", "")[:150],
            "solved_at": goal.get("solved_at", ""),
            "created_at": now.isoformat(),
        })

    all_links = kept_links + new_links
    _save_links(all_links)

    log(f"done — {len(new_links)} new links, {len(kept_links)} kept, {expired} expired, {len(all_links)} total")
    return {"new": len(new_links), "kept": len(kept_links), "expired": expired, "total": len(all_links)}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
