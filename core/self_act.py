
import time
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Package-relative import (requires running as: python3 -m core.self_act)
from .gpt_reasoner import gpt_reasoner
from .event_ledger import log_event
from .agent_loop import agent_loop
from .providers.router import call_ollama as _call_ollama

BASE = Path(__file__).resolve().parents[1]         # ~/Echo
MEM  = BASE / "memory"
STATE_FILE = MEM / "core_state_reasoning.json"
SYS_STATE_FILE = MEM / "core_state_system.json"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"reasoning_history": [], "knowledge": {}, "X_flags": []}

def save_state(state):
    # Cap history and knowledge to last 50 entries to prevent unbounded growth
    if len(state.get("reasoning_history", [])) > 50:
        state["reasoning_history"] = state["reasoning_history"][-50:]
    if len(state.get("knowledge", {})) > 50:
        keys = list(state["knowledge"].keys())
        state["knowledge"] = {k: state["knowledge"][k] for k in keys[-50:]}
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

def load_system_state():
    if SYS_STATE_FILE.exists():
        try:
            return json.loads(SYS_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}
def update_income_status():
    import re as _re
    from datetime import datetime
    doc_path = Path(__file__).resolve().parents[1] / "memory" / "income_knowledge.md"
    if not doc_path.exists():
        return
    doc = doc_path.read_text()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    changed = False
    # Golem investigation closed 2026-04-23 — zero market demand, not a connectivity issue.
    # Do not update Golem status or generate Golem tasks. See memory/known_gaps.md.
    new_golem = f"**Echo's current status:** CLOSED — investigation ended 2026-04-24, market demand problem not connectivity | _checked {now}_"
    doc, n = _re.subn(r"\*\*Echo.s current status:\*\* (?:ACTIVE|CLOSED) — (?:node running|investigation).*", new_golem, doc)
    if n: changed = True
    devto_count = 1
    try:
        log_path = Path(__file__).resolve().parents[1] / "logs" / "devto_publish.log"
        if log_path.exists():
            devto_count = max(1, log_path.read_text().lower().count("published"))
    except Exception:
        pass
    scheduled_note = ""
    try:
        import subprocess
        r = subprocess.run(["systemctl", "--user", "is-active", "echo-devto-publish.timer"], capture_output=True, text=True)
        if r.stdout.strip() == "active":
            scheduled_note = ", 1 scheduled Tuesday 2026-03-17"
    except Exception:
        pass
    s = "s" if devto_count != 1 else ""
    new_devto = f"**Echo's current status:** ACTIVE — {devto_count} article{s} published{scheduled_note} | _checked {now}_"
    doc, n = _re.subn(r"\*\*Echo.s current status:\*\* ACTIVE — \d+ article.*", new_devto, doc)
    if n: changed = True
    doc, n = _re.subn(r"_Last updated: [\d\- :]+_", f"_Last updated: {now}_", doc)
    if n: changed = True
    if changed:
        doc_path.write_text(doc)
        print(f"[income_status] Updated income_knowledge.md at {now}")

def _parse_and_add_task(result) -> None:
    """
    If Echo's result contains ADD_TASK: <description>, add it to standing_tasks.json
    and notify Andrew via Telegram.
    """
    result_str = str(result or "")
    marker = "ADD_TASK:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    # Extract the task description — everything after ADD_TASK: until newline or end
    raw = result_str[idx + len(marker):].strip()
    task_desc = raw.split("\n")[0].strip().strip('"').strip("'")
    if not task_desc or len(task_desc) < 10:
        return

    # Guard: reject corrupted/error-serialized tasks and closed investigations
    _desc_lower = task_desc.lower()
    if any(x in task_desc for x in ['HTTPConnection', 'Traceback', '<description>', "read timeout"]):
        print(f"[self_act] ADD_TASK rejected (corrupted payload): {task_desc[:60]}")
        return
    if 'golem' in _desc_lower:
        print(f"[self_act] ADD_TASK rejected (Golem closed): {task_desc[:60]}")
        return
    # Guard: low-quality / repetitive task patterns
    BAD_TASK_PHRASES = [
        "echo_maintenance.py",        # script doesn't exist
        "review and update the todo", # too vague, not actionable
        "update the todo list",
        "verify system status",       # too generic
        "already in place",           # meta-commentary leaked into output
        "no new task is need",
        "this task is already",
        "qwen2.5:32b integration",    # not a real task
        "draft documentation",        # too vague without specific file
        "prepare documentation",
        "general integration plan",
        "general outline",
    ]
    for phrase in BAD_TASK_PHRASES:
        if phrase in _desc_lower:
            print(f"[self_act] ADD_TASK rejected (low quality — '{phrase}'): {task_desc[:60]}")
            return
    # Guard: rate limit — check only, write AFTER successful add
    import time as _time
    rate_file = BASE / "memory" / "task_rate.json"
    try:
        now_ts = _time.time()
        if rate_file.exists():
            rate_data = json.loads(rate_file.read_text())
            last_ts = rate_data.get("last_task_ts", 0)
            if now_ts - last_ts < 14400:  # 4 hours
                print(f"[self_act] ADD_TASK rate-limited (last task {int((now_ts-last_ts)/3600)}h ago)")
                return
    except Exception as e:
        print(f"[self_act] ADD_TASK rate check failed: {e}")
        return  # fail safe

    try:
        standing_file = BASE / "memory/standing_tasks.json"
        data = json.loads(standing_file.read_text())

        # Deduplicate — don't add if very similar task already exists
        existing_texts = [t.get("task", "").lower() for t in data["tasks"]]
        if any(task_desc.lower()[:40] in t for t in existing_texts):
            print(f"[self_act] ADD_TASK skipped (duplicate): {task_desc[:60]}")
            return

        from datetime import datetime
        new_id = f"self_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        new_task = {
            "id": new_id,
            "task": task_desc,
            "weight": 1.0,
            "wins": 0,
            "losses": 0,
            "min_weight": 0.3,
            "max_weight": 2.0,
            "self_generated": True,
            "added_at": datetime.now().isoformat(),
        }
        data["tasks"].append(new_task)
        tmp = standing_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(standing_file)
        # Stamp rate limit only after successful write
        try:
            rate_file.write_text(json.dumps({"last_task_ts": now_ts}))
        except Exception:
            pass
        print(f"[self_act] ADD_TASK: '{task_desc[:80]}'")

        # Notify Andrew via Telegram
        try:
            from core.notifier import notify
            notify(
                "Echo added a task",
                f"She scheduled: \"{task_desc[:160]}\"",
                urgent=False,
                phone=True,
            )
        except Exception as _e:
            print(f"[self_act] notify failed: {_e}")

        try:
            log_event("action", "self_act", f"self_generated task: {task_desc[:100]}", score=1.0)
        except Exception:
            pass

    except Exception as e:
        print(f"[self_act] ADD_TASK error: {e}")


def _parse_and_add_gap(result) -> None:
    """
    If Echo's result contains ADD_GAP: <description>, append it to known_gaps.md
    under the appropriate priority section.
    """
    result_str = str(result or "")
    marker = "ADD_GAP:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    raw = result_str[idx + len(marker):].strip()
    gap_desc = raw.split("\n")[0].strip().strip('"').strip("'")
    if not gap_desc or len(gap_desc) < 10:
        return

    # Guard: reject corrupted payloads
    if any(x in gap_desc for x in ['HTTPConnection', 'Traceback', '<description>', "read timeout"]):
        print(f"[self_act] ADD_GAP rejected (corrupted payload): {gap_desc[:60]}")
        return
    # Guard: Golem investigation is closed
    if 'golem' in gap_desc.lower():
        print(f"[self_act] ADD_GAP rejected (Golem closed): {gap_desc[:60]}")
        return
    # Guard: hallucinated file-not-found errors (Echo cannot actually read files in this context)
    _low = gap_desc.lower()
    BAD_PHRASES = [
        "not found", "unable to", "not available", "not accessible",
        "not properly", "no specific gaps", "need to verify", "need to confirm",
        "cannot be prepared", "does not exist", "missing or not properly",
        "memory/", "logs/self_act", "dispatch_history", "echo_state.json",
        "not currently captured", "without this", "general outline",
    ]
    for phrase in BAD_PHRASES:
        if phrase in _low:
            print(f"[self_act] ADD_GAP rejected (low quality — '{phrase}'): {gap_desc[:60]}")
            return
    # Guard: rate limit — check only, write AFTER successful add
    import time as _time
    gap_rate_file = BASE / "memory" / "gap_rate.json"
    try:
        now_ts = _time.time()
        if gap_rate_file.exists():
            rate_data = json.loads(gap_rate_file.read_text())
            last_gap_ts = rate_data.get("last_gap_ts", 0)
            if now_ts - last_gap_ts < 21600:  # 6 hours
                print(f"[self_act] ADD_GAP rate-limited (last gap {int((now_ts-last_gap_ts)/3600)}h ago)")
                return
    except Exception as e:
        print(f"[self_act] ADD_GAP rate check failed: {e}")
        return  # fail safe — don't add gap if rate check is broken

    try:
        gaps_file = BASE / "memory" / "known_gaps.md"
        existing = gaps_file.read_text() if gaps_file.exists() else ""

        # Deduplicate
        if gap_desc.lower()[:40] in existing.lower():
            print(f"[self_act] ADD_GAP skipped (duplicate): {gap_desc[:60]}")
            return

        from datetime import datetime
        entry = f"\n- {gap_desc}  _(identified by Echo {datetime.now().strftime('%Y-%m-%d %H:%M')})_"

        # Append under High Priority section if present, else at end
        if "## High Priority Gaps" in existing:
            updated = existing.replace(
                "## High Priority Gaps",
                f"## High Priority Gaps{entry}",
                1
            )
        else:
            updated = existing + f"\n{entry}\n"

        tmp = gaps_file.with_suffix(".tmp")
        tmp.write_text(updated)
        tmp.rename(gaps_file)
        # Stamp rate limit only after successful write
        try:
            gap_rate_file.write_text(json.dumps({"last_gap_ts": now_ts}))
        except Exception:
            pass

        print(f"[self_act] ADD_GAP: '{gap_desc[:80]}'")

        try:
            from core.notifier import notify
            notify("Echo found a gap", f"\"{gap_desc[:160]}\"", urgent=False, phone=True)
        except Exception:
            pass

    except Exception as e:
        print(f"[self_act] ADD_GAP error: {e}")


def _parse_and_add_build(result) -> None:
    """
    If Echo's result contains ADD_BUILD: <description>, generate a script
    and notify Andrew via Telegram for approval. She proposes — he approves.
    Build must be grounded in known_gaps.md — no hallucinated proposals.
    """
    result_str = str(result or "")
    marker = "ADD_BUILD:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    raw = result_str[idx + len(marker):].strip()
    description = raw.split("\n")[0].strip().strip('"').strip("'")
    if not description or len(description) < 10:
        return

    # Guard: must relate to Echo's actual domain
    ALLOWED_DOMAINS = [
        "trading", "alpaca", "crypto", "stock", "fiverr", "lead", "reddit",
        "telegram", "notifier", "monitor", "alert", "backup", "ollama",
        "content", "article", "devto", "dev.to", "beehiiv", "income",
        "discord", "ram", "memory", "disk", "timer", "systemd", "scheduler",
        "session", "checkpoint", "summary", "digest", "log", "error",
        "notion", "briefing", "governor", "vast", "gpu",
    ]
    desc_lower = description.lower()
    if not any(kw in desc_lower for kw in ALLOWED_DOMAINS):
        print(f"[self_act] ADD_BUILD rejected (out of domain): {description[:80]}")
        return

    # Guard: must match something in known_gaps.md
    gaps_file = BASE / "memory/known_gaps.md"
    if gaps_file.exists():
        gaps_text = gaps_file.read_text().lower()
        # Check if at least 2 words from the description appear in the gaps file
        words = [w for w in desc_lower.split() if len(w) > 4]
        matches = sum(1 for w in words if w in gaps_text)
        if matches < 2:
            print(f"[self_act] ADD_BUILD rejected (not in known_gaps.md — {matches} word matches): {description[:80]}")
            return

    # Rate limit — max one build proposal per hour
    try:
        rate_file = BASE / "memory" / "self_build_rate.json"
        from datetime import datetime, timedelta
        now = datetime.now()
        if rate_file.exists():
            rate = json.loads(rate_file.read_text())
            last = datetime.fromisoformat(rate.get("last_build", "2000-01-01"))
            if (now - last).total_seconds() < 3600:
                print(f"[self_act] ADD_BUILD rate-limited, skipping: {description[:60]}")
                return
        tmp = rate_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_build": now.isoformat()}))
        tmp.rename(rate_file)
    except Exception as e:
        print(f"[self_act] ADD_BUILD rate check error: {e}")

    print(f"[self_act] ADD_BUILD triggered: {description[:80]}")

    try:
        from core.self_build import generate, read_pending_code
        build = generate(description)
        name = build.get("name", "unknown")
        syntax = "ok" if build.get("syntax_ok") else f"SYNTAX ERROR: {build.get('syntax_error','')}"
        code = read_pending_code(name)
        preview = code[:2000] + ("\n...(truncated)" if len(code) > 2000 else "")

        msg = (
            f"Echo proposes a build: {name}\n"
            f"Reason: {description[:120]}\n"
            f"Syntax: {syntax}\n\n"
            f"{preview}\n\n"
            f"/approve {name}  or  /reject {name}"
        )
        try:
            from core.notifier import notify
            notify("Echo wants to build", msg[:4000], urgent=False, phone=True)
        except Exception as _e:
            print(f"[self_act] ADD_BUILD notify failed: {_e}")

        try:
            log_event("action", "self_act", f"self_proposed build: {name} — {description[:80]}", score=1.0)
        except Exception:
            pass

    except Exception as e:
        print(f"[self_act] ADD_BUILD error: {e}")


def _parse_and_add_content(result) -> None:
    """
    If Echo's result contains ADD_CONTENT: <title> | <angle>, queue it in
    content_strategy.json for content_gen to pick up and write.
    Format: ADD_CONTENT: Article Title Here | one sentence angle
    """
    result_str = str(result or "")
    marker = "ADD_CONTENT:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    raw = result_str[idx + len(marker):].strip().split("\n")[0].strip()
    if not raw or len(raw) < 10:
        return

    # Parse title | angle
    parts = raw.split("|", 1)
    title = parts[0].strip().strip('"').strip("'")
    angle = parts[1].strip() if len(parts) > 1 else ""

    if not title or len(title) < 8:
        return

    strategy_file = BASE / "memory/content_strategy.json"
    try:
        cs = json.loads(strategy_file.read_text()) if strategy_file.exists() else {"queue": []}

        # Deduplicate by title
        existing_titles = [q.get("title", "").lower() for q in cs.get("queue", [])]
        if title.lower() in existing_titles:
            print(f"[self_act] ADD_CONTENT skipped (duplicate): {title[:60]}")
            return

        # Cap queue at 8 pending items
        pending = [q for q in cs.get("queue", []) if q.get("status") in ("queued", "next")]
        if len(pending) >= 8:
            print(f"[self_act] ADD_CONTENT skipped (queue full, {len(pending)} items): {title[:60]}")
            return

        import uuid
        entry = {
            "id": f"echo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "title": title,
            "angle": angle,
            "status": "queued",
            "source": "self_act",
            "created_at": datetime.now().isoformat(),
        }
        cs.setdefault("queue", []).append(entry)

        tmp = strategy_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(cs, indent=2))
        tmp.rename(strategy_file)

        print(f"[self_act] ADD_CONTENT queued: '{title[:60]}' — {angle[:60]}")

        try:
            log_event("action", "self_act", f"content queued: {title[:80]}", score=1.0)
        except Exception:
            pass

    except Exception as e:
        print(f"[self_act] ADD_CONTENT error: {e}")


def _update_task_weight(task_text: str, result) -> None:
    """Score the standing task that produced this result and adjust its weight."""
    try:
        standing_file = BASE / "memory/standing_tasks.json"
        data = json.loads(standing_file.read_text())
        result_str = str(result).strip() if result else ""

        # Determine success: result has substance and isn't an error/empty
        failure_signals = [
            "error", "timeout", "failed", "exception", "i cannot",
            "i don't know", "unable to", "no data", "not found", ""
        ]
        too_short = len(result_str) < 30
        is_failure = too_short or any(
            s in result_str.lower()[:120] for s in failure_signals[:8]
        )
        success = not is_failure

        # Match task by text substring
        task_lower = str(task_text).lower()
        matched = False
        for t in data["tasks"]:
            t_text = t.get("task", "").lower()
            t_id = t.get("id", "").lower()
            if t_text and (t_text[:40] in task_lower or task_lower[:40] in t_text or t_id in task_lower):
                if success:
                    t["wins"] = t.get("wins", 0) + 1
                    t["weight"] = min(t.get("max_weight", 2.0), t.get("weight", 1.0) + 0.05)
                else:
                    t["losses"] = t.get("losses", 0) + 1
                    if not t.get("failure_immune", False):
                        t["weight"] = max(t.get("min_weight", 0.1), t.get("weight", 1.0) - 0.05)
                matched = True
                break

        if matched:
            tmp = standing_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.rename(standing_file)
    except Exception:
        pass


def reasoning_cycle():
    core_state = load_state()
    system_state = load_system_state()
    core_state["system_state"] = system_state

    # ---- deterministic queue behavior ----
    # Generate fresh flags from system state before processing
    fresh = generate_flags(core_state)
    existing = core_state.get("X_flags", [])
    for flag in fresh:
        if flag not in existing:
            existing.append(flag)
    core_state["X_flags"] = []
    flags = list(existing)  # clear immediately so it cannot “stick” if we crash mid-run

    for x_flag in flags:
        prompt_flag = x_flag
        if str(x_flag).lower().startswith("summarize:"):
            ss = system_state or {}
            facts = {
                "updated_at": ss.get("updated_at"),
                "core": ss.get("core", {}),
                "services": ss.get("services", {}),
                "timers": ss.get("timers", {}),
                "last": ss.get("last", {}),
                "errors": ss.get("errors", []),
            }
            prompt_flag = (
                "summarize: current Echo system state in ONE paragraph. "
                "Use ONLY these facts (no guessing): " + json.dumps(facts, default=str)
            )

        # Use agent_loop for tool-capable reasoning; fall back to gpt_reasoner if it fails
        try:
            system_prompt = (
                "You are Echo. You are running an autonomous background reasoning cycle.\n"
                "Complete the task below using your tools if needed.\n"
                "Be concrete and specific. State what you found or did — not what you would do.\n"
                "If you check a tool, summarize what it returned.\n"
                "Do not restart services unless specifically asked to investigate a failure.\n\n"
                "Special tokens you can emit at the end of your response:\n"
                "ADD_TASK: <description> — add a new standing task to your queue\n"
                "ADD_GAP: <description> — record a gap or missing capability you noticed\n"
                "ADD_BUILD: <description> — propose a script to close a gap listed in memory/known_gaps.md ONLY. Do NOT invent new ideas.\n"
                "ADD_CONTENT: <title> | <one sentence angle> — queue an article topic you identified as worth writing\n"
                "Only emit a token if you have a specific, concrete reason based on what you observed.\n"
                "ADD_BUILD is ONLY valid if the build directly addresses a gap already recorded in known_gaps.md."
            )
            result = agent_loop(
                prompt=str(prompt_flag),
                system_prompt=system_prompt,
                call_ollama_fn=_call_ollama,
                model="qwen2.5:7b",
                timeout=180.0,
                max_iterations=3,
                auto_approve_safe=True,
            )
        except Exception as _e:
            result = gpt_reasoner(prompt_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        if "income_knowledge" in str(x_flag):
            update_income_status()
        try:
            log_event("reasoning", "self_act", str(x_flag)[:200], data=result if isinstance(result, dict) else str(result))
        except Exception:
            pass

        # Score this task directly — did the result have real substance?
        _update_task_weight(x_flag, result)

        # Check if Echo proposed a new task to add to her queue
        _parse_and_add_task(result)

        # Check if Echo identified a new gap
        _parse_and_add_gap(result)

        # Check if Echo proposed a new build
        _parse_and_add_build(result)

        # Check if Echo identified content worth writing
        _parse_and_add_content(result)

        print(f"Processed {x_flag}: {result}")

    save_state(core_state)


def generate_flags(core_state: dict) -> list:
    """
    Generate X_flags based on current system state.
    Called at the start of every reasoning cycle to ensure queue never runs dry.
    """
    flags = []
    system = core_state.get("system_state", {})
    errors = system.get("errors", [])
    timers = system.get("timers", {})
    workers = system.get("workers", {})

    # Flag any errors
    for err in errors[:2]:
        flag = f"investigate error: {str(err)[:80]}"
        if flag not in core_state.get("knowledge", {}):
            flags.append(flag)

    # Flag stale workers
    for name, info in workers.items():
        if isinstance(info, dict) and info.get("stale"):
            flag = f"investigate stale worker: {name}"
            if flag not in core_state.get("knowledge", {}):
                flags.append(flag)

    # Flag inactive timers
    for name, active in timers.items():
        if not active:
            flag = f"investigate inactive timer: {name}"
            if flag not in core_state.get("knowledge", {}):
                flags.append(flag)

    # Load standing tasks from file — adaptive, not hardcoded
    standing_file = BASE / "memory/standing_tasks.json"
    try:
        import json as _json
        standing_data = _json.loads(standing_file.read_text())
        tasks = standing_data.get("tasks", [])
        # Weight-based selection — higher weight = more frequent
        import random as _random
        weights = [max(t.get("weight", 1.0), 0.1) for t in tasks]
        total = sum(weights)
        normalized = [w/total for w in weights]
        idx = core_state.get('_standing_idx', 0) % len(tasks)
        core_state['_standing_idx'] = idx + 1
        task = tasks[idx]["task"]
        # Update cycle count
        standing_data["total_cycles"] = standing_data.get("total_cycles", 0) + 1
        standing_file.write_text(_json.dumps(standing_data, indent=2))
    except Exception as e:
        # Fallback to basic task if file missing
        task = "summarize: current Echo system state in ONE paragraph"
    if task not in flags:
        flags.append(task)
    return flags



if __name__ == "__main__":
    # worker mode
    if "--once" in sys.argv:
        print("Echo self_act: once")
        reasoning_cycle()
        sys.exit(0)

    # legacy loop mode (not used by systemd worker)
    while True:
        print("Echo alive")
        reasoning_cycle()
        time.sleep(10)
