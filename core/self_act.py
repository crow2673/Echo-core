
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
    # Guard: off-domain tasks — same domain check as ADD_BUILD
    TASK_ALLOWED_DOMAINS = [
        "trading", "alpaca", "crypto", "stock", "fiverr", "lead", "reddit",
        "telegram", "notifier", "monitor", "alert", "backup", "ollama",
        "content", "article", "devto", "dev.to", "beehiiv", "income",
        "discord", "ram", "memory", "disk", "timer", "systemd", "log",
        "notion", "briefing", "governor", "vast", "gpu", "registry", "ledger",
        "income_knowledge", "standing_tasks", "world_context", "echo", "self",
    ]
    TASK_BLOCKED = [
        "business plan", "launching a small tech business", "freelance writing",
        "financial projection", "pitch deck", "investor", "recruit a team",
    ]
    if any(b in _desc_lower for b in TASK_BLOCKED):
        print(f"[self_act] ADD_TASK rejected (blocked topic): {task_desc[:60]}")
        return
    if not any(kw in _desc_lower for kw in TASK_ALLOWED_DOMAINS):
        print(f"[self_act] ADD_TASK rejected (out of domain): {task_desc[:60]}")
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


def _build_tier(description: str) -> str:
    """
    Classify a build description into an autonomy tier.

    auto   — new tools/ utility (monitor, alert, scanner, log reader, backup helper).
             Echo builds AND deploys immediately. Notifies after the fact.
    notify — touches data sources, memory writers, or external APIs.
             Echo builds, notifies Andrew, auto-deploys after 2 hours if not rejected.
    gate   — anything that touches core/, modifies existing deployed files,
             makes financial orders, or changes trading logic.
             Always requires explicit /approve. Never auto-deploys.
    """
    desc_lower = description.lower()

    # Hard gate — these never auto-deploy
    GATE_SIGNALS = [
        "core/", "alpaca order", "place order", "submit order",
        "buy signal", "sell signal", "open position", "close position",
        "crypto_brain", "trade_brain", "dispatcher",
        "modify existing", "replace existing", "rewrite existing", "patch existing",
        "trading strategy", "trading logic", "trading algorithm",
    ]
    if any(s in desc_lower for s in GATE_SIGNALS):
        return "gate"

    # Auto tier — safe new utility scripts
    AUTO_SIGNALS = [
        "monitor", "alert", "scan", "log", "backup", "digest",
        "check", "report", "watch", "tracker", "summary",
    ]
    if any(s in desc_lower for s in AUTO_SIGNALS):
        return "auto"

    # Everything else — notify Andrew, auto-deploy after 2h if no rejection
    return "notify"


def _parse_and_add_build(result) -> None:
    """
    If Echo's result contains ADD_BUILD: <description>, generate a script
    and deploy it according to its autonomy tier:
      auto  — build + deploy immediately, notify after
      notify — build + notify Andrew, auto-deploy after 2h if no /reject
      gate  — build + notify Andrew, wait for explicit /approve
    """
    result_str = str(result or "")
    marker = "ADD_BUILD:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    raw = result_str[idx + len(marker):].strip()
    description = raw.split("\n")[0].strip().strip('"').strip("'")

    # ADD_BUILD format: <what> | goal: <goal/income impact> | reach: <how it reaches Andrew or customer>
    parts = [p.strip() for p in description.split("|")]
    if len(parts) < 3:
        print(f"[self_act] ADD_BUILD rejected (missing goal/reach — need 3 pipe-separated parts): {description[:80]}")
        return
    goal_part = next((p for p in parts if p.lower().startswith("goal:")), None)
    reach_part = next((p for p in parts if p.lower().startswith("reach:")), None)
    if not goal_part or not reach_part:
        print(f"[self_act] ADD_BUILD rejected (missing goal: or reach: fields): {description[:80]}")
        return
    if len(goal_part) < 15 or len(reach_part) < 15:
        print(f"[self_act] ADD_BUILD rejected (goal/reach too vague): {description[:80]}")
        return
    description = parts[0]
    if not description or len(description) < 10:
        return

    ALLOWED_DOMAINS = [
        "trading", "alpaca", "crypto", "stock", "fiverr", "lead", "reddit",
        "telegram", "notifier", "monitor", "alert", "backup", "ollama",
        "content", "article", "devto", "dev.to", "beehiiv", "income",
        "discord", "ram", "memory", "disk", "timer", "systemd", "scheduler",
        "session", "checkpoint", "digest", "log", "error",
        "notion", "briefing", "governor", "vast", "gpu",
    ]
    BLOCKED_TOPICS = [
        "business plan", "financial projection", "executive summary",
        "market analysis", "business model", "pitch deck", "investor",
        "resume", "cover letter", "personal finance", "budget template",
    ]
    desc_lower = description.lower()
    if any(blocked in desc_lower for blocked in BLOCKED_TOPICS):
        print(f"[self_act] ADD_BUILD rejected (blocked topic): {description[:80]}")
        return
    if not any(kw in desc_lower for kw in ALLOWED_DOMAINS):
        print(f"[self_act] ADD_BUILD rejected (out of domain): {description[:80]}")
        return

    gaps_file = BASE / "memory/known_gaps.md"
    if gaps_file.exists():
        gaps_text = gaps_file.read_text().lower()
        words = [w for w in desc_lower.split() if len(w) > 5]
        matches = sum(1 for w in words if w in gaps_text)
        if matches < 4:
            print(f"[self_act] ADD_BUILD rejected (not in known_gaps.md — {matches} word matches): {description[:80]}")
            return

    # Rate limit — max one build per hour
    try:
        rate_file = BASE / "memory" / "self_build_rate.json"
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

    tier = _build_tier(description)
    print(f"[self_act] ADD_BUILD triggered (tier={tier}): {description[:80]}")

    try:
        from core.self_build import generate, read_pending_code, approve
        build = generate(description)
        if not build.get("syntax_ok"):
            print(f"[self_act] ADD_BUILD syntax failed — not deploying: {build.get('syntax_error','')}")
            return

        name = build.get("name", "unknown")
        code = read_pending_code(name)
        preview = code[:1500] + ("\n...(truncated)" if len(code) > 1500 else "")

        if tier == "auto":
            # Deploy immediately — notify after the fact
            result_deploy = approve(name, target_dir="tools")
            if result_deploy.get("ok"):
                msg = (
                    f"Echo deployed: {name}\n"
                    f"What: {description[:120]}\n"
                    f"Deployed to: {result_deploy['path']}\n\n"
                    f"To undo: /reject {name}"
                )
                print(f"[self_act] AUTO-DEPLOYED: {name}")
            else:
                msg = f"Echo tried to auto-deploy {name} but it failed: {result_deploy.get('error','')}"
                print(f"[self_act] AUTO-DEPLOY FAILED: {name}")
            try:
                from core.notifier import notify
                notify("Echo deployed a build", msg[:4000], urgent=False, phone=True)
            except Exception:
                pass

        elif tier == "notify":
            # Build done — notify Andrew, stamp a 2h deadline, auto-deploy later
            build_reg_path = BASE / "builds" / "registry.json"
            try:
                reg = json.loads(build_reg_path.read_text())
                reg[name]["auto_deploy_after"] = (
                    datetime.now() + __import__("datetime").timedelta(hours=2)
                ).isoformat()
                tmp = build_reg_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(reg, indent=2))
                tmp.rename(build_reg_path)
            except Exception:
                pass
            msg = (
                f"Echo built (auto-deploys in 2h): {name}\n"
                f"What: {description[:120]}\n"
                f"Goal: {goal_part[5:].strip()[:100]}\n\n"
                f"{preview}\n\n"
                f"To block: /reject {name}"
            )
            try:
                from core.notifier import notify
                notify("Echo built — deploying in 2h", msg[:4000], urgent=False, phone=True)
            except Exception:
                pass

        else:  # gate
            msg = (
                f"Echo wants to build (requires approval): {name}\n"
                f"What: {description[:120]}\n"
                f"Goal: {goal_part[5:].strip()[:100]}\n"
                f"Reach: {reach_part[6:].strip()[:100]}\n\n"
                f"{preview}\n\n"
                f"/approve {name}  or  /reject {name}"
            )
            try:
                from core.notifier import notify
                notify("Echo wants to build", msg[:4000], urgent=False, phone=True)
            except Exception:
                pass

        try:
            log_event("action", "self_act", f"build tier={tier}: {name} — {description[:80]}", score=1.0)
        except Exception:
            pass

    except Exception as e:
        print(f"[self_act] ADD_BUILD error: {e}")


def _parse_and_revise_build(result) -> None:
    """
    If Echo's result contains REVISE_BUILD: <build_name>, re-generate the script
    using the existing code + review_notes as context, overwrite the pending file,
    and notify Andrew for re-approval.
    Format: REVISE_BUILD: <build_name>
    """
    result_str = str(result or "")
    marker = "REVISE_BUILD:"
    idx = result_str.find(marker)
    if idx == -1:
        return

    raw = result_str[idx + len(marker):].strip().split("\n")[0].strip()
    build_name = raw.split("|")[0].strip()
    if not build_name or len(build_name) < 5:
        return

    try:
        import re as _re, py_compile, tempfile, os as _os
        from core.self_build import load_registry, save_registry, SYSTEM_PROMPT
        from core.providers.router import call_ollama

        reg = load_registry()

        # Partial name match — build names are truncated slugs
        matched = None
        for name in reg:
            if build_name in name or name in build_name:
                matched = name
                break
        if not matched:
            print(f"[self_act] REVISE_BUILD: no build found for '{build_name}'")
            return

        build = reg[matched]
        if build.get("status") not in ("needs_revision",):
            print(f"[self_act] REVISE_BUILD: '{matched}' status={build.get('status')} — only revise needs_revision builds")
            return

        pending_path = Path(build["path"])
        if not pending_path.exists():
            print(f"[self_act] REVISE_BUILD: pending file missing: {pending_path}")
            return

        original_code = pending_path.read_text()
        review_notes = build.get("review_notes", "Fix the issues in this script.")
        description = build.get("description", matched)

        prompt = (
            f"Revise this Python script based on the review feedback.\n\n"
            f"ORIGINAL SCRIPT:\n{original_code}\n\n"
            f"REVIEW FEEDBACK (apply these exact fixes):\n{review_notes}\n\n"
            f"Output ONLY the corrected Python. No explanation. No markdown fences."
        )

        print(f"[self_act] REVISE_BUILD: revising '{matched}'")

        try:
            code = call_ollama(
                prompt=prompt,
                model="qwen2.5:32b",
                timeout=600.0,
                system_prompt=SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[self_act] REVISE_BUILD LLM error: {e}")
            return

        code = _re.sub(r"^```python\s*", "", code, flags=_re.MULTILINE)
        code = _re.sub(r"^```\s*$", "", code, flags=_re.MULTILINE)
        code = code.strip()
        if not code.startswith("#"):
            code = f"#!/usr/bin/env python3\n{code}"

        # Syntax check — do not overwrite with broken code
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf:
            tf.write(code)
            tf_path = tf.name
        try:
            py_compile.compile(tf_path, doraise=True)
            syntax_ok = True
        except py_compile.PyCompileError as e:
            print(f"[self_act] REVISE_BUILD: syntax error in revision — {e}")
            syntax_ok = False
        finally:
            _os.unlink(tf_path)

        if not syntax_ok:
            return

        # Atomic overwrite
        tmp = pending_path.with_suffix(".tmp")
        tmp.write_text(code)
        tmp.rename(pending_path)

        build["status"] = "pending"
        build["revised_at"] = datetime.now().isoformat()
        build["revision_note"] = "Self-revised by Echo based on review_notes"
        reg[matched] = build
        save_registry(reg)

        preview = code[:1500] + ("\n...(truncated)" if len(code) > 1500 else "")
        msg = (
            f"Echo revised: {matched}\n"
            f"Syntax: ok\n\n"
            f"{preview}\n\n"
            f"/approve {matched}  or  /reject {matched}"
        )
        try:
            from core.notifier import notify
            notify("Echo revised a build", msg[:4000], urgent=False, phone=True)
        except Exception:
            pass

        print(f"[self_act] REVISE_BUILD: done — '{matched}' ready for /approve")

    except Exception as e:
        print(f"[self_act] REVISE_BUILD error: {e}")


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


def _build_grounded_context(task: str) -> str:
    """
    Detect what real data a task references and inject it into the prompt.
    Without this, llama3.1 hallucinates file contents — long fluent lies.
    Returns a context block to prepend to the prompt, or "" if nothing relevant.
    """
    task_lower = task.lower()
    sections = []

    def _read(path, label, max_chars=2000):
        try:
            p = BASE / path
            if p.exists():
                content = p.read_text().strip()[:max_chars]
                sections.append(f"=== {label} ===\n{content}")
        except Exception:
            pass

    def _cmd(cmd, label, max_chars=1500):
        try:
            import subprocess
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = (r.stdout + r.stderr).strip()[:max_chars]
            if out:
                sections.append(f"=== {label} ===\n{out}")
        except Exception:
            pass

    # File references
    if any(k in task_lower for k in ["income_knowledge", "income path", "income stream"]):
        _read("memory/income_knowledge.md", "income_knowledge.md")

    if any(k in task_lower for k in ["known_gaps", "gap", "missing capability"]):
        _read("memory/known_gaps.md", "known_gaps.md")

    if any(k in task_lower for k in ["registry.json", "services are", "services running", "verify all listed"]):
        _read("registry.json", "registry.json", max_chars=3000)
        _cmd(["systemctl", "--user", "list-units", "echo-*", "--no-pager", "--plain"],
             "systemctl echo units")

    if any(k in task_lower for k in ["world_context", "trending topic", "write an article"]):
        _read("memory/world_context.md", "world_context.md")

    if any(k in task_lower for k in ["standing_tasks", "task queue", "task list"]):
        _read("memory/standing_tasks.json", "standing_tasks.json", max_chars=2000)

    if any(k in task_lower for k in ["system state", "system health", "services", "timers"]):
        _read("memory/core_state_system.json", "core_state_system.json", max_chars=2000)

    if any(k in task_lower for k in ["ledger", "recent wins", "recent losses", "event"]):
        _read("memory/cascade_ledger.json", "cascade_ledger.json (last entries)", max_chars=2000)

    if any(k in task_lower for k in ["disk", "disk usage", "disk space"]):
        _cmd(["df", "-h", str(Path.home())], "disk usage")

    if any(k in task_lower for k in ["memory usage", "ram", "cpu usage"]):
        _cmd(["free", "-h"], "memory usage")

    if any(k in task_lower for k in ["trading", "trade", "crypto", "stock", "position"]):
        _read("memory/crypto_trade_log.json", "crypto_trade_log.json", max_chars=1500)
        _read("memory/income_knowledge.md", "income_knowledge.md", max_chars=1000)

    if not sections:
        return ""

    return (
        "REAL DATA — use only this, do not invent or assume anything outside it:\n\n"
        + "\n\n".join(sections)
        + "\n\n"
    )


def _score_outcome(result: str) -> str:
    """
    Return 'win', 'neutral', or 'loss' based on verifiable output, not fluency.

    win    — emitted a verifiable token (ADD_BUILD/ADD_GAP/ADD_TASK/ADD_CONTENT/REVISE_BUILD)
             that passed downstream guards, meaning real work was proposed
    loss   — hallucination signals: invented tools, wrong years, fabricated hostnames,
             or references to data that doesn't exist in Echo's codebase
    neutral — produced text only; no token, no hallucination caught
    """
    result_str = str(result or "").strip()

    # Win: emitted a real action token (guards already filtered bad ones upstream)
    ACTION_TOKENS = ["ADD_BUILD:", "ADD_GAP:", "ADD_TASK:", "ADD_CONTENT:", "REVISE_BUILD:"]
    if any(tok in result_str for tok in ACTION_TOKENS):
        return "win"

    # Loss: hallucination signals — things that don't exist in Echo's environment
    HALLUCINATION_SIGNALS = [
        "sysmon",           # fake monitoring tool
        "host1", "host2", "host3",  # invented hostnames
        "2023-02", "2023-03", "2022-",  # wrong years (Echo started 2026)
        "asset xyz",        # fake asset
        "ledger database",  # no such tool — it's a JSON file
        "google analytics", # not integrated
        "backup_config",    # fake tool
        "echo_maintenance.py",  # script doesn't exist
        "i will run a series",  # classic hallucinated future-promise
        "i have initiated a 24-hour",  # hallucinated commitment
        "i've started a monitoring cycle",  # can't do that, it's one-shot
        "i will run the following commands",  # no tool loop exists
    ]
    result_lower = result_str.lower()
    if any(sig in result_lower for sig in HALLUCINATION_SIGNALS):
        return "loss"

    return "neutral"


def _update_task_weight(task_text: str, result) -> None:
    """Score the standing task that produced this result and adjust its weight."""
    try:
        standing_file = BASE / "memory/standing_tasks.json"
        data = json.loads(standing_file.read_text())
        result_str = str(result).strip() if result else ""

        outcome = _score_outcome(result_str)

        # Match task by text substring
        task_lower = str(task_text).lower()
        matched = False
        for t in data["tasks"]:
            t_text = t.get("task", "").lower()
            t_id = t.get("id", "").lower()
            if t_text and (t_text[:40] in task_lower or task_lower[:40] in t_text or t_id in task_lower):
                if outcome == "win":
                    t["wins"] = t.get("wins", 0) + 1
                    t["weight"] = min(t.get("max_weight", 2.0), t.get("weight", 1.0) + 0.1)
                elif outcome == "loss":
                    t["losses"] = t.get("losses", 0) + 1
                    if not t.get("failure_immune", False):
                        t["weight"] = max(t.get("min_weight", 0.1), t.get("weight", 1.0) - 0.2)
                # neutral: no weight change
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

        # Ground the prompt in real data before sending to LLM.
        # Without this, llama3.1 fabricates file contents and tool outputs.
        grounded_context = _build_grounded_context(str(prompt_flag))
        grounded_prompt = grounded_context + str(prompt_flag) if grounded_context else str(prompt_flag)

        # Use agent_loop for tool-capable reasoning; fall back to gpt_reasoner if it fails
        try:
            system_prompt = (
                "You are Echo. You are running an autonomous background reasoning cycle.\n"
                "The REAL DATA block above contains the actual current state of the system — "
                "use it as your only source of truth. Do not invent data, tools, or outcomes.\n"
                "Be concrete and specific. State what you found — not what you would do.\n"
                "Do not promise future monitoring cycles or scheduled tasks — you are one-shot.\n"
                "Do not reference tools that don't exist (sysmon, backup_config, ledger database, etc).\n\n"
                "Special tokens you can emit at the end of your response:\n"
                "ADD_TASK: <description> — add a new standing task to your queue\n"
                "ADD_GAP: <description> — record a gap or missing capability you noticed in the REAL DATA\n"
                "ADD_BUILD: <what> | goal: <how it generates income or moves Echo's goals forward> | reach: <how it reaches Andrew or a customer> — propose a build grounded in known_gaps.md.\n"
                "ADD_CONTENT: <title> | <one sentence angle> — queue an article topic you identified as worth writing\n"
                "REVISE_BUILD: <build_name> — re-generate a pending build that has status=needs_revision, applying its review_notes. Only emit if you are specifically processing a build revision flag.\n"
                "Only emit a token if you have a specific, concrete reason based on what you observed in the REAL DATA.\n"
                "ADD_BUILD requires all three parts separated by pipes. A build with no goal or no reach is not worth proposing.\n"
                "ADD_BUILD must be about Echo's own systems: trading, monitoring, alerts, content, leads, backups, memory.\n"
                "NEVER emit ADD_BUILD for: business plans, templates, financial documents, or anything unrelated to Echo's codebase."
            )
            result = agent_loop(
                prompt=grounded_prompt,
                system_prompt=system_prompt,
                call_ollama_fn=_call_ollama,
                model="llama3.1:latest",
                timeout=180.0,
                max_iterations=3,
                auto_approve_safe=True,
            )
        except Exception as _e:
            result = gpt_reasoner(grounded_prompt, core_state)
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

        # Check if Echo needs to revise an existing build
        _parse_and_revise_build(result)

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

    # Auto-deploy any notify-tier builds whose 2h window has passed
    try:
        from core.self_build import load_registry, save_registry, approve as _approve
        _reg = load_registry()
        _changed = False
        for _name, _b in _reg.items():
            if _b.get("status") == "pending" and _b.get("auto_deploy_after"):
                _deadline = datetime.fromisoformat(_b["auto_deploy_after"])
                if datetime.now() >= _deadline:
                    _r = _approve(_name, target_dir="tools")
                    if _r.get("ok"):
                        print(f"[self_act] auto-deployed (2h passed): {_name}")
                        try:
                            from core.notifier import notify as _notify
                            _notify("Echo auto-deployed", f"Deployed {_name} (no rejection in 2h)", urgent=False, phone=True)
                        except Exception:
                            pass
                    _changed = True
        if _changed:
            pass  # approve() already updates registry
    except Exception:
        pass

    # Flag any needs_revision builds so Echo self-corrects them
    try:
        from core.self_build import load_registry as _load_reg
        _reg = _load_reg()
        for _name, _b in _reg.items():
            if _b.get("status") == "needs_revision":
                _notes = _b.get("review_notes", "")[:100]
                _flag = f"revise build '{_name}': {_notes}"
                if _flag not in core_state.get("knowledge", {}):
                    flags.append(_flag)
                    break  # one revision per cycle
    except Exception:
        pass

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
