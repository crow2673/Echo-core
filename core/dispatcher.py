#!/usr/bin/env python3
"""
core/dispatcher.py — Phase 3 decision pipeline for all worker launches.

Five-step pipeline before any worker runs:
  1. System health   — hardware constraints, conflicting workers
  2. Context check   — timing, cooldowns, preconditions
  3. Historical      — compare to last run, what changed, did it progress
  4. Echo's judgment — qwen2.5:7b reasons over state + history brief
  5. Validation      — does the data support the decision?

Usage:
    from core.dispatcher import dispatch
    dispatch("demand_scanner")

    or CLI:
    python3 -m core.dispatcher demand_scanner
"""

import json
import os
import urllib.request
import subprocess
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
HISTORY_FILE = BASE / "memory/dispatch_history.json"
STATE_FILE = BASE / "memory/echo_state.json"
LOG_FILE = BASE / "logs/dispatcher.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

# ── Worker registry ───────────────────────────────────────────────────────────
# Each entry defines how to run the worker and what context checks apply.
WORKERS = {
    "demand_scanner": {
        "cmd": [sys.executable, str(BASE / "tools/demand_scanner.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 3300,       # ~55 min — scanner has its own per-subreddit cooldown
        "cooldown_state_key": None,     # dispatcher-level cooldown (not per-subreddit)
        "wave": 1,
        "heavy": False,                 # does not need GPU
        "description": "Reddit lead scanner for Fiverr gig — scans 12 subreddits, scores leads 1-10",
        "progress_metric": "new_leads", # what to check to see if it progressed
    },
    "self_act": {
        "cmd": [sys.executable, "-m", "core.self_act", "--once"],
        "cwd": str(BASE),
        "cooldown_seconds": 270,        # ~4.5 min
        "wave": 1,
        "heavy": True,                  # uses GPU (qwen2.5:7b)
        "description": "Background reasoning cycle — processes standing tasks and X_flags",
        "progress_metric": "reasoning",
    },
    "initiative": {
        "cmd": [sys.executable, str(BASE / "core/initiative_engine.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 840,        # ~14 min — fires every 15 min
        "wave": 1,
        "heavy": False,
        "description": "Proactive trigger watcher — stop loss proximity, runway, RSI, milestones, leads",
        "progress_metric": "alerts_fired",
    },

    # ── Wave 2 ────────────────────────────────────────────────────────────────
    "daily_briefing": {
        "cmd": [sys.executable, "-m", "core.daily_briefing"],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # 20 hours — runs once per day
        "wave": 2,
        "heavy": True,                  # calls Ollama for speech synthesis
        "skip_judgment": True,          # LLM spirals into "no progress" self-reinforcing skips — time_window + cooldown are sufficient gates
        "description": "Morning briefing — speaks system health, P&L, tasks, and priorities at 8:10am",
        "progress_metric": "briefing_spoken",
        "time_window": (6, 12),         # only valid between 6am and noon
    },
    "session_checkpoint": {
        "cmd": [sys.executable, "-m", "core.session_checkpoint"],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # 20 hours — runs once per night
        "wave": 2,
        "heavy": False,
        "skip_judgment": True,          # cooldown is the only gate; LLM confuses "24h ago" with "too soon"
        "description": "Nightly checkpoint — writes session_summary.json from CHANGELOG, trade log, regret patterns",
        "progress_metric": "checkpoint_written",
        "time_window": (22, 4),         # only valid between 10pm and 4am (wraps midnight)
    },
    "content_gen": {
        "cmd": [sys.executable, str(BASE / "core/content_pipeline.py"), "--generate"],
        "cwd": str(BASE),
        "cooldown_seconds": 79200,      # 22 hours — at most once per day
        "wave": 2,
        "heavy": True,                  # calls Ollama for article generation
        "skip_judgment": True,          # LLM self-reinforces skips ("3 consecutive skips = skip again") — cooldown gates it
        "description": "Content pipeline — generates dev.to draft from content_strategy queue",
        "progress_metric": "draft_created",
    },

    "devto_publish": {
        "cmd": [sys.executable, str(BASE / "echo_devto_publisher.py"), "--from-queue"],
        "cwd": str(BASE),
        "cooldown_seconds": 518400,     # 6 days — Tuesday catch-up slot
        "wave": 2,
        "heavy": False,                 # only publishes pre-approved drafts — no Ollama
        "skip_judgment": True,
        "description": "Weekly dev.to publisher — publishes Andrew-approved drafts only (telegram_approver is primary path)",
        "progress_metric": "article_published",
        "time_window": (8, 11),         # only valid between 8am and 11am (Tuesday window)
    },

    # ── Wave 2.5 — Reconciler (runs after every trading cycle) ───────────────
    "alpaca_reconciler": {
        "cmd": [sys.executable, "-m", "core.alpaca_reconciler"],
        "cwd": str(BASE),
        "cooldown_seconds": 7200,       # 2 hours — runs after each trader cycle
        "wave": 2,
        "heavy": False,
        "skip_judgment": True,          # deterministic — cooldown is the only gate
        "description": "Alpaca P&L reconciler — rebuilds cascade_ledger and income_knowledge from real fills",
        "progress_metric": "reconciled_at",
    },

    # ── Wave 3 — Echo-built monitors ─────────────────────────────────────────
    "temperature_monitor": {
        "cmd": [sys.executable, str(BASE / "tools/temperature_monitor.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 3300,       # ~55 min — hourly check
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # cooldown handles timing; LLM confuses low temp with skip
        "description": "CPU temperature monitor — alerts via Telegram if Core 0 exceeds 70°C",
        "progress_metric": None,
    },
    "cpu_monitor": {
        "cmd": [sys.executable, str(BASE / "tools/cpu_monitor.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 3300,       # ~55 min — hourly check, off-peak only
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # cooldown handles timing; LLM skips at low CPU (wrong)
        "description": "CPU usage monitor — alerts if usage >80% during off-peak hours (10pm-6am)",
        "progress_metric": None,
    },
    "system_health": {
        "cmd": [sys.executable, str(BASE / "tools/system_health.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # 20 hours — daily check
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # deterministic — cooldown is the only gate needed
        "description": "Daily health check — journalctl error scan, disk/mem/network, alerts on issues",
        "progress_metric": None,
    },
    "ram_monitor": {
        "cmd": [sys.executable, "-m", "core.ram_monitor"],
        "cwd": str(BASE),
        "cooldown_seconds": 270,        # 4.5 min — fires every 5 min
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # high-frequency monitor; LLM call overhead not worth it
        "description": "RAM monitor — alerts before OOM kills qwen2.5:32b; checks swap pressure too",
        "progress_metric": None,
    },
    "task_pruner": {
        "cmd": [sys.executable, "-m", "core.task_pruner"],
        "cwd": str(BASE),
        "cooldown_seconds": 604800,     # 7 days — weekly strategic decay pass
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # deterministic rule-based pruning, no judgment needed
        "description": "Task queue pruner — removes stale/duplicate self-generated tasks, caps queue at 60",
        "progress_metric": None,
    },
    "temporal_mirror": {
        "cmd": [sys.executable, "-m", "core.temporal_mirror"],
        "cwd": str(BASE),
        "cooldown_seconds": 86400,      # daily — runs overnight to link causal pairs
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,          # structural matching, no judgment needed
        "description": "Temporal mirror — links failure events to resolution events in decision trace",
        "progress_metric": None,
        "time_window": (0, 5),          # run overnight 12am–5am only
    },
    "opportunity_hunter": {
        "cmd": [sys.executable, str(BASE / "tools/opportunity_hunter.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 3600,       # hourly — live opportunities expire fast
        "wave": 1,
        "heavy": True,                  # generates proposals with qwen2.5:7b
        "skip_judgment": False,
        "description": "Hunt real paying work: Freelancer.com API, GitHub bounties, Reddit forhire",
        "progress_metric": "new_proposals",
    },
    "income_scanner": {
        "cmd": [sys.executable, "-m", "core.income_scanner"],
        "cwd": str(BASE),
        "cooldown_seconds": 7200,       # every 2 hours — reads all data, finds work, does it
        "wave": 1,
        "heavy": True,                  # uses qwen2.5:7b
        "skip_judgment": False,         # Echo should judge — she's deciding what to work on
        "description": "Income scanner — reads all Echo data, finds best income action, executes it",
        "progress_metric": "income_action",
    },
    "gumroad_publisher": {
        "cmd": [sys.executable, str(BASE / "tools/gumroad_publisher.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 86400,      # daily — new builds listed as products
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "List Echo's built tools as Gumroad products — passive digital product income",
        "progress_metric": None,
    },
    "affiliate_injector": {
        "cmd": [sys.executable, str(BASE / "tools/affiliate_injector.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 43200,      # twice daily
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Inject affiliate links into published Dev.to articles — passive referral income",
        "progress_metric": None,
    },
    "newsletter_composer": {
        "cmd": [sys.executable, str(BASE / "tools/newsletter_composer.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 86400,      # daily check, sends weekly
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Compose and send weekly automation newsletter via Beehiiv — subscription income",
        "progress_metric": None,
        "time_window": (8, 10),         # send morning only
    },
    "account_bootstrap": {
        "cmd": [sys.executable, "-m", "core.account_bootstrap"],
        "cwd": str(BASE),
        "cooldown_seconds": 43200,      # retry every 12h if something failed last time
        "wave": 1,
        "heavy": True,                  # uses Playwright + browser = needs VRAM headroom
        "skip_judgment": True,          # deterministic: run if any credential is missing
        "description": "Create missing platform accounts — Reddit, Gumroad, Beehiiv, Dev.to",
        "progress_metric": None,
    },
    "log_anomaly": {
        "cmd": [sys.executable, "-m", "core.log_anomaly", "score"],
        "cwd": str(BASE),
        "cooldown_seconds": 840,        # timer is 15 min; allow slight drift
        "wave": 3,
        "heavy": False,                 # CPU-only model/scorer
        "skip_judgment": True,          # deterministic monitor; cooldown is enough
        "description": "Log sequence anomaly scorer — flags surprising Echo/systemd log transitions",
        "progress_metric": None,
        "lock_file": str(BASE / "logs/log_anomaly.lock"),
        "notify_dispatcher": False,
    },
    "log_anomaly_train": {
        "cmd": [
            sys.executable, "-m", "core.log_anomaly", "train",
            "--since", "72 hours ago",
            "--epochs", "8",
        ],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # daily-ish
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Daily CPU-only training pass for the log sequence anomaly model",
        "progress_metric": None,
        "time_window": (2, 5),          # train during quiet overnight hours
        "lock_file": str(BASE / "logs/log_anomaly.lock"),
        "notify_dispatcher": False,
        "timeout_seconds": 1800,
    },
    "homeostasis": {
        "cmd": [sys.executable, str(BASE / "tools/homeostasis_check.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 270,        # timer is 5 min; allow slight drift
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Reliability homeostasis — audits drift, restarts safe monitors, alerts for protected failures",
        "progress_metric": None,
        "lock_file": str(BASE / "logs/homeostasis.lock"),
        "notify_dispatcher": False,
    },
    "autonomy_model": {
        "cmd": [sys.executable, str(BASE / "tools/autonomy_model.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 840,        # refresh before each life-loop window
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Autonomy model — ranks no-human actions, human gates, trust, memory sprawl, and maturity gaps",
        "progress_metric": None,
        "lock_file": str(BASE / "logs/autonomy_model.lock"),
        "notify_dispatcher": False,
    },
    "life_loop": {
        "cmd": [sys.executable, str(BASE / "tools/life_loop.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 840,        # timer is 15 min; allow slight drift
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Life loop — records Echo's evidence-grounded current state and next priority",
        "progress_metric": None,
        "lock_file": str(BASE / "logs/life_loop.lock"),
        "notify_dispatcher": False,
    },
    "outcome_loop": {
        "cmd": [sys.executable, str(BASE / "tools/outcome_loop.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 840,        # timer is 15 min; allow slight drift
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Outcome loop — verifies expected local outcomes and writes success/failure evidence",
        "progress_metric": None,
        "lock_file": str(BASE / "logs/outcome_loop.lock"),
        "notify_dispatcher": False,
    },
    "growth_engine": {
        "cmd": [sys.executable, str(BASE / "tools/growth_engine.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # daily-ish
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Growth engine — ranks evidence-backed improvement proposals without auto-building code",
        "progress_metric": None,
        "time_window": (3, 6),
        "lock_file": str(BASE / "logs/growth_engine.lock"),
        "notify_dispatcher": False,
    },
    "growth_bridge": {
        "cmd": [sys.executable, str(BASE / "tools/growth_bridge.py")],
        "cwd": str(BASE),
        "cooldown_seconds": 72000,      # daily-ish
        "wave": 3,
        "heavy": False,
        "skip_judgment": True,
        "description": "Growth bridge — promotes top safe growth proposals into reviewed build requests",
        "progress_metric": None,
        "time_window": (4, 7),
        "lock_file": str(BASE / "logs/growth_bridge.lock"),
        "notify_dispatcher": False,
    },
}

# ── User presence ─────────────────────────────────────────────────────────────
def is_user_idle() -> bool:
    try:
        p = BASE / "memory/user_presence.json"
        if p.exists():
            d = json.loads(p.read_text())
            age = (datetime.now() - datetime.fromisoformat(d.get("updated_at", "2000-01-01"))).total_seconds()
            if age < 300:  # presence file must be fresh (< 5 min old)
                return d.get("is_idle", False)
    except Exception:
        pass
    return False


# ── History I/O ───────────────────────────────────────────────────────────────
def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return {"workers": {}}


def save_history(history: dict):
    # Cap each worker's history to last 100 entries
    for w in history.get("workers", {}).values():
        if len(w.get("runs", [])) > 100:
            w["runs"] = w["runs"][-100:]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_name(f"{HISTORY_FILE.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(json.dumps(history, indent=2, default=str))
        os.replace(tmp, HISTORY_FILE)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def get_worker_history(history: dict, worker: str) -> dict:
    return history.get("workers", {}).get(worker, {})


# ── State I/O ─────────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        raw = STATE_FILE.read_text()
        d = json.loads(raw)
        if d.get("valid"):
            return d
    except Exception:
        pass
    return {}


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    print(msg, flush=True)
    logging.info(msg)


def record_run(history: dict, worker: str, decision: str, reason: str,
               steps_passed: list, step_failed: int | None,
               progressed: bool, validation_flags: list):
    workers = history.setdefault("workers", {})
    w = workers.setdefault(worker, {"runs": []})
    if decision != "dry_run":  # dry-runs don't set last_run — no cooldown pollution
        w["last_run"] = datetime.now().isoformat()
    w["last_decision"] = decision
    w["last_reason"] = reason
    w["last_progressed"] = progressed
    if decision == "skip":
        w["consecutive_skips"] = w.get("consecutive_skips", 0) + 1
        w["consecutive_runs"] = 0
    else:
        w["consecutive_runs"] = w.get("consecutive_runs", 0) + 1
        w["consecutive_skips"] = 0
    w["runs"].append({
        "ts": datetime.now().isoformat(),
        "decision": decision,
        "reason": reason,
        "steps_passed": steps_passed,
        "step_failed": step_failed,
        "progressed": progressed,
        "validation_flags": validation_flags,
    })


# ── VRAM flush ────────────────────────────────────────────────────────────────
def _flush_idle_ollama_models(keep_model: str = "qwen2.5:7b") -> int:
    """
    Unload any Ollama models that are NOT the one we're about to use.
    Returns MB freed (estimated). Called before launching heavy workers.
    qwen2.5:32b at Q4_K_M = 10.4GB VRAM — kills self_act every time it stays loaded.
    """
    freed_mb = 0
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/ps",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        models = data.get("models", [])
        for m in models:
            name = m.get("name", "")
            if name == keep_model:
                continue
            vram_bytes = m.get("size_vram", 0)
            # Unload by calling generate with keep_alive=0
            payload = json.dumps({"model": name, "keep_alive": 0}).encode()
            unload_req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(unload_req, timeout=10):
                    pass
                freed_mb += vram_bytes // (1024 * 1024)
                log(f"[dispatcher] unloaded {name} from VRAM (~{freed_mb}MB freed)")
            except Exception:
                pass
    except Exception:
        pass
    return freed_mb


# ── Step 1: System Health ─────────────────────────────────────────────────────
def step1_system_health(worker: str, cfg: dict, state: dict) -> tuple[bool, str]:
    system = state.get("system", {})
    vram_used = system.get("vram_used_mb", 0)
    vram_total = system.get("vram_total_mb", 12288)
    vram_free = vram_total - vram_used

    # Heavy workers need GPU headroom — qwen2.5:7b runs fine in 3.5GB.
    # If VRAM is tight, try flushing idle models before giving up.
    if cfg.get("heavy") and vram_free < 3500:
        freed = _flush_idle_ollama_models(keep_model="qwen2.5:7b")
        if freed > 0:
            vram_free += freed
            log(f"[dispatcher] VRAM flush freed {freed}MB — now ~{vram_free}MB free")
        if vram_free < 3500:
            return False, f"insufficient VRAM: {vram_free}MB free, need 3500MB (heavy worker)"

    # Check if another heavy worker is already running (match on script path, not name)
    if cfg.get("heavy"):
        heavy_workers = [w for w, c in WORKERS.items() if c.get("heavy") and w != worker]
        for hw in heavy_workers:
            hw_cfg = WORKERS[hw]
            # Use the actual script/module from cmd as the pgrep pattern
            cmd_parts = hw_cfg.get("cmd", [])
            pattern = next((p for p in cmd_parts if p not in (sys.executable, "-m", "--once", "--generate")), hw)
            check = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True
            )
            if check.returncode == 0:
                pids = check.stdout.strip().split()
                # Exclude our own PID
                own_pid = str(os.getpid())
                other_pids = [p for p in pids if p != own_pid]
                if other_pids:
                    return False, f"heavy worker '{hw}' already running (PID {other_pids[0]})"

    # Check last_errors in state for this worker
    last_errors = state.get("last_errors", [])
    worker_errors = [e for e in last_errors if worker in str(e).lower()]
    if len(worker_errors) >= 3:
        return False, f"worker had {len(worker_errors)} recent errors in echo_state.json"

    return True, "ok"


# ── Step 2: Context Check ─────────────────────────────────────────────────────
def step2_context(worker: str, cfg: dict, history: dict) -> tuple[bool, str]:
    w_hist = get_worker_history(history, worker)
    last_run_str = w_hist.get("last_run")

    if last_run_str:
        try:
            last_run = datetime.fromisoformat(last_run_str)
            elapsed = (datetime.now() - last_run).total_seconds()
            cooldown = cfg.get("cooldown_seconds", 0)
            # Soldier mode: when user is idle, cut cooldowns in half for execution workers
            if is_user_idle() and not cfg.get("skip_judgment") and worker in ("self_act", "auto_act", "initiative", "demand_scanner"):
                cooldown = max(60, cooldown // 2)
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed)
                return False, f"cooldown active — {remaining}s remaining (last run {int(elapsed)}s ago)"
        except Exception:
            pass

    # Worker-specific checks
    if worker == "demand_scanner":
        demand_state_file = BASE / "memory/demand_state.json"
        if demand_state_file.exists():
            try:
                ds = json.loads(demand_state_file.read_text())
                # All subreddits on cooldown = no point running
                from datetime import datetime as dt
                now_ts = dt.now().timestamp()
                all_cooled = all(
                    (now_ts - dt.fromisoformat(v).timestamp()) < 3300
                    for k, v in ds.items()
                    if k.startswith("last_scan_") and v
                )
                if all_cooled and len(ds) >= 5:
                    return False, "all subreddits still on cooldown"
            except Exception:
                pass

    if worker == "initiative":
        # Don't fire if last run was less than 13 minutes ago (timer is 15 min)
        if last_run_str:
            try:
                elapsed = (datetime.now() - datetime.fromisoformat(last_run_str)).total_seconds()
                if elapsed < 780:
                    return False, f"initiative fired {int(elapsed)}s ago, timer cadence is 900s"
            except Exception:
                pass

    # Wave 2 time window checks
    if worker == "daily_briefing":
        hour = datetime.now().hour
        if not (6 <= hour < 12):
            return False, f"outside morning window — current hour={hour}, window=6-12"
        # Confirm checkpoint ran last night (briefing needs fresh session context)
        checkpoint_file = BASE / "memory/session_summary.json"
        if checkpoint_file.exists():
            try:
                age = (datetime.now() - datetime.fromtimestamp(checkpoint_file.stat().st_mtime)).total_seconds()
                if age > 172800:  # 48h — briefing still useful with day-old context
                    return False, f"session_summary.json is {int(age/3600)}h old — checkpoint may not have run"
            except Exception:
                pass

    if worker == "session_checkpoint":
        hour = datetime.now().hour
        if not (hour >= 22 or hour < 4):
            return False, f"outside night window — current hour={hour}, window=22-4"

    if worker == "content_gen":
        # Skip if content_strategy queue has no items ready
        strategy_file = BASE / "memory/content_strategy.json"
        if strategy_file.exists():
            try:
                cs = json.loads(strategy_file.read_text())
                ready = [q for q in cs.get("queue", []) if q.get("status") in ("next", "queued")]
                if not ready:
                    return False, "content_strategy queue is empty — no topics to generate"
            except Exception:
                pass
        # Skip if draft queue already has pending drafts
        draft_queue = BASE / "content/draft_queue.json"
        if draft_queue.exists():
            try:
                queue = json.loads(draft_queue.read_text())
                pending = [d for d in queue if d.get("status") == "pending"]
                if len(pending) >= 2:
                    return False, f"draft queue already has {len(pending)} pending drafts"
            except Exception:
                pass

    return True, "ok"


# ── Step 3: Historical Comparison ─────────────────────────────────────────────
def step3_historical(worker: str, state: dict, history: dict) -> dict:
    w_hist = get_worker_history(history, worker)
    runs = w_hist.get("runs", [])

    result = {
        "has_history": bool(runs),
        "last_progressed": w_hist.get("last_progressed", None),
        "consecutive_skips": w_hist.get("consecutive_skips", 0),
        "consecutive_runs": w_hist.get("consecutive_runs", 0),
        "total_runs": len(runs),
        "delta": {},
        "summary": "",
    }

    if not runs:
        result["summary"] = "no prior runs — first execution"
        return result

    last = runs[-1]
    result["last_decision"] = last.get("decision", "unknown")
    result["last_reason"] = last.get("reason", "")

    # Build delta from state context
    cascade = state.get("cascade", {})
    income = state.get("income", {})

    if worker == "demand_scanner":
        leads_file = BASE / "memory/demand_leads.json"
        lead_count = 0
        try:
            leads = json.loads(leads_file.read_text())
            lead_count = len(leads)
        except Exception:
            pass
        result["delta"]["lead_queue_size"] = lead_count
        result["summary"] = (
            f"Last run: {last.get('ts', 'unknown')[:16]} — "
            f"progressed={last.get('progressed')} — "
            f"current lead queue: {lead_count}"
        )

    elif worker == "self_act":
        consec_skips = result["consecutive_skips"]
        consec_runs = result["consecutive_runs"]
        result["summary"] = (
            f"Last run: {last.get('ts', 'unknown')[:16]} — "
            f"decision={last.get('decision')} — "
            f"consecutive_runs={consec_runs} consecutive_skips={consec_skips}"
        )

    elif worker == "initiative":
        result["summary"] = (
            f"Last run: {last.get('ts', 'unknown')[:16]} — "
            f"progressed={last.get('progressed')} — "
            f"portfolio={income.get('portfolio_value', 'unknown')}"
        )

    elif worker == "daily_briefing":
        result["summary"] = (
            f"Last briefing: {last.get('ts', 'unknown')[:16]} — "
            f"progressed={last.get('progressed')}"
        )

    elif worker == "session_checkpoint":
        checkpoint_file = BASE / "memory/session_summary.json"
        checkpoint_age = "unknown"
        try:
            if checkpoint_file.exists():
                age_h = (datetime.now() - datetime.fromtimestamp(
                    checkpoint_file.stat().st_mtime)).total_seconds() / 3600
                checkpoint_age = f"{age_h:.1f}h ago"
        except Exception:
            pass
        result["summary"] = (
            f"Last checkpoint: {last.get('ts', 'unknown')[:16]} — "
            f"session_summary.json written {checkpoint_age}"
        )

    elif worker == "content_gen":
        draft_queue = BASE / "content/draft_queue.json"
        pending_count = 0
        try:
            if draft_queue.exists():
                queue = json.loads(draft_queue.read_text())
                pending_count = len([d for d in queue if d.get("status") == "pending"])
        except Exception:
            pass
        result["summary"] = (
            f"Last content gen: {last.get('ts', 'unknown')[:16]} — "
            f"pending drafts: {pending_count}"
        )

    # Flag stagnation: 3+ consecutive non-progressing runs
    if len(runs) >= 3:
        recent = runs[-3:]
        if all(not r.get("progressed") for r in recent):
            result["stagnating"] = True
            result["summary"] += " ⚠️ stagnating (3 runs without progress)"

    return result


# ── Step 4: Echo's Judgment ───────────────────────────────────────────────────
def step4_echo_judgment(worker: str, cfg: dict, state: dict, hist_summary: dict) -> tuple[bool, str]:
    if cfg.get("skip_judgment"):
        return True, "monitor — cooldown is sole gate, judgment skipped"

    try:
        sys.path.insert(0, str(BASE))
        from core.providers.router import call_ollama

        system_health = state.get("system_health", "unknown")
        system = state.get("system", {})
        cascade = state.get("cascade", {})

        brief = (
            f"You are Echo. Decide whether to run the worker '{worker}' right now.\n\n"
            f"Worker description: {cfg['description']}\n\n"
            f"System state: health={system_health}, "
            f"cpu={system.get('cpu_pct', '?')}%, "
            f"ram={system.get('ram_pct', '?')}%, "
            f"vram_free={(system.get('vram_total_mb', 12288) - system.get('vram_used_mb', 0))}MB\n\n"
            f"History: {hist_summary.get('summary', 'no history')}\n"
            f"Consecutive skips: {hist_summary.get('consecutive_skips', 0)}\n"
            f"Last progressed: {hist_summary.get('last_progressed', 'unknown')}\n"
        )

        if cascade:
            brief += f"Trading: {json.dumps(cascade, default=str)[:300]}\n"

        brief += (
            "\nAnswer with YES or NO followed by one sentence reason."
            "\nExample: YES — conditions look good."
            "\nExample: NO — last 5 runs produced nothing."
            "\nNOTE: CPU under 30% and RAM under 80% is NOT a reason to skip."
            "\nOnly skip if there is a concrete, specific reason related to this worker's purpose."
        )

        response = call_ollama(
            prompt=brief,
            model="llama3.1:latest",
            timeout=60.0,
            system_prompt="You are Echo. Give a direct YES or NO decision. Be concise. Do not skip workers just because system load is low.",
        )

        response = (response or "").strip()
        if not response:
            return True, "no response from model — defaulting to run"
        decision = response.upper().startswith("YES")
        # Ensure reason is always populated
        reason = response[:200] if response else f"{'run' if decision else 'skip'} (no reason given)"
        return decision, reason

    except Exception as e:
        # Timeout or failure → default to RUN (fail open, not closed)
        return True, f"judgment timed out or failed ({e}) — defaulting to run"


# ── Step 5: Data Validation ───────────────────────────────────────────────────
def step5_validate(worker: str, decision: bool, state: dict, hist: dict) -> list[str]:
    flags = []
    w_hist = get_worker_history(hist, worker)
    runs = w_hist.get("runs", [])

    if decision:  # Echo said RUN — look for reasons not to
        if worker in ("demand_scanner",):
            recent_no_progress = sum(
                1 for r in runs[-5:] if not r.get("progressed")
            )
            if recent_no_progress >= 4:
                flags.append(f"Echo said RUN but last {recent_no_progress}/5 runs produced no leads")

        if worker == "self_act":
            cascade = state.get("cascade", {})
            # If multiple trading losses recently, flag that reasoning might be missing it
            recent_losses = cascade.get("recent_losses", 0)
            if recent_losses and recent_losses >= 3:
                flags.append(f"Echo said RUN but {recent_losses} recent trading losses — check if self_act is addressing this")

    else:  # Echo said SKIP — look for reasons it should run
        consec_skips = w_hist.get("consecutive_skips", 0)
        if consec_skips >= 5:
            flags.append(f"Echo said SKIP but worker has been skipped {consec_skips} consecutive times")

    return flags


# ── Notify Andrew (Wave 3 only) ───────────────────────────────────────────────
def notify_wave3(worker: str, decision: bool, reason: str):
    try:
        from core.notifier import notify
        action = "APPROVED" if decision else "SKIPPED"
        notify(
            f"Dispatcher: {worker} {action}",
            reason[:200],
            urgent=False,
            phone=True,
        )
    except Exception as e:
        log(f"[dispatcher] notify failed: {e}")


def acquire_worker_lock(cfg: dict):
    lock_file = cfg.get("lock_file")
    if not lock_file:
        return None
    import fcntl
    path = Path(lock_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        handle.close()
        return False


# ── Main dispatch function ────────────────────────────────────────────────────
def dispatch(worker: str, dry_run: bool = False) -> bool:
    """
    Run the five-step pipeline for the given worker.
    Returns True if worker was launched, False if skipped.
    dry_run=True logs the decision without launching.
    """
    if worker not in WORKERS:
        log(f"[dispatcher] ERROR: unknown worker '{worker}'")
        return False

    cfg = WORKERS[worker]
    history = load_history()
    state = load_state()
    steps_passed = []
    step_failed = None
    validation_flags = []

    log(f"[dispatcher] evaluating '{worker}' {'(dry-run)' if dry_run else ''}")

    # ── Step 1: System Health ─────────────────────────────────────────────────
    ok, reason = step1_system_health(worker, cfg, state)
    if not ok:
        log(f"[dispatcher] SKIP {worker}: system_health — {reason}")
        record_run(history, worker, "skip", f"system_health: {reason}",
                   steps_passed, 1, False, [])
        save_history(history)
        return None
    steps_passed.append(1)
    log(f"[dispatcher] step1 pass: {worker}")

    # ── Step 2: Context Check ─────────────────────────────────────────────────
    ok, reason = step2_context(worker, cfg, history)
    if not ok:
        log(f"[dispatcher] SKIP {worker}: context — {reason}")
        record_run(history, worker, "skip", f"context: {reason}",
                   steps_passed, 2, False, [])
        save_history(history)
        return None
    steps_passed.append(2)
    log(f"[dispatcher] step2 pass: {worker}")

    # ── Step 3: Historical Comparison ─────────────────────────────────────────
    hist_summary = step3_historical(worker, state, history)
    steps_passed.append(3)
    log(f"[dispatcher] step3: {hist_summary['summary']}")

    # ── Step 4: Echo's Judgment ───────────────────────────────────────────────
    # Force-run if judgment has blocked the same worker too many consecutive times.
    # A self-reinforcing skip loop ("I was skipped, therefore skip again") is worse
    # than running a worker that does nothing useful.
    consec_skips = hist_summary.get("consecutive_skips", 0)
    if consec_skips >= 5 and not cfg.get("skip_judgment"):
        decision = True
        echo_reason = f"force-run: {consec_skips} consecutive skips — breaking self-reinforcing skip loop"
        log(f"[dispatcher] step4 OVERRIDE {worker}: {echo_reason}")
    else:
        decision, echo_reason = step4_echo_judgment(worker, cfg, state, hist_summary)
    steps_passed.append(4)
    log(f"[dispatcher] step4 judgment: {'RUN' if decision else 'SKIP'} — {echo_reason[:100]}")

    # ── Step 5: Data Validation ───────────────────────────────────────────────
    validation_flags = step5_validate(worker, decision, state, history)
    steps_passed.append(5)
    if validation_flags:
        for flag in validation_flags:
            log(f"[dispatcher] VALIDATE {worker}: ⚠️ {flag}")

    # ── Notify Andrew for Wave 3 workers ──────────────────────────────────────
    if cfg.get("wave", 1) >= 3 and cfg.get("notify_dispatcher", True):
        notify_wave3(worker, decision, echo_reason)

    # ── Final decision ────────────────────────────────────────────────────────
    if not decision:
        log(f"[dispatcher] SKIP {worker}: judgment — {echo_reason[:100]}")
        record_run(history, worker, "skip", f"judgment: {echo_reason}",
                   steps_passed, 4, False, validation_flags)
        save_history(history)
        return None

    if dry_run:
        log(f"[dispatcher] DRY-RUN {worker}: would run — {echo_reason[:100]}")
        record_run(history, worker, "dry_run", echo_reason,
                   steps_passed, None, False, validation_flags)
        save_history(history)
        return True

    worker_lock = acquire_worker_lock(cfg)
    if worker_lock is False:
        reason = "another mutually exclusive worker is already running"
        log(f"[dispatcher] SKIP {worker}: lock — {reason}")
        record_run(history, worker, "skip", f"lock: {reason}",
                   steps_passed, None, False, validation_flags)
        save_history(history)
        return None

    # ── Launch worker ─────────────────────────────────────────────────────────
    log(f"[dispatcher] RUN {worker}: launching — {echo_reason[:80]}")
    worker_timeout = int(cfg.get("timeout_seconds") or (900 if cfg.get("heavy") else 600))
    try:
        start = time.time()
        result = subprocess.run(
            cfg["cmd"],
            cwd=cfg.get("cwd", str(BASE)),
            timeout=worker_timeout,
            capture_output=False,
        )
        elapsed = round(time.time() - start, 1)
        progressed = result.returncode == 0
        log(f"[dispatcher] {worker} finished in {elapsed}s — exit={result.returncode}")
        record_run(history, worker, "run", echo_reason,
                   steps_passed, None, progressed, validation_flags)
        save_history(history)
        return progressed
    except subprocess.TimeoutExpired:
        log(f"[dispatcher] {worker} timed out after {worker_timeout}s")
        record_run(history, worker, "timeout", f"worker exceeded {worker_timeout}s",
                   steps_passed, None, False, validation_flags)
        save_history(history)
        return False
    except Exception as e:
        log(f"[dispatcher] {worker} launch error: {e}")
        record_run(history, worker, "error", str(e),
                   steps_passed, None, False, validation_flags)
        save_history(history)
        return False
    finally:
        if worker_lock:
            try:
                worker_lock.close()
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 -m core.dispatcher <worker_name>")
        print(f"Available workers: {', '.join(WORKERS.keys())}")
        sys.exit(1)
    worker_name = sys.argv[1]
    dry = "--dry-run" in sys.argv
    success = dispatch(worker_name, dry_run=dry)
    # None = deliberate skip (cooldown/context/judgment) — not a failure
    sys.exit(0 if (success or success is None) else 1)
