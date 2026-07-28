#!/usr/bin/env python3
"""
core/telegram_intake.py — Inbound Telegram command and message handler.

Polls for new messages from Andrew's chat_id only.
Routes:
  /status    — system snapshot from echo_state.json
  /trades    — open positions and realized P&L
  /leads     — top uncontacted Reddit leads (score >= 7)
  /tasks     — current standing tasks and weights
  /health    — timer health, stale services
  /help      — list commands
  anything else → drops into echo_memory.json capsule queue for daemon

Runs every 30s via echo-telegram-intake.timer.
Offset tracked in memory/telegram_state.json to avoid reprocessing.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import logging
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / "logs/telegram_intake.log"
LOG_FILE.parent.mkdir(exist_ok=True)
STATE_FILE = BASE / "memory/telegram_state.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

# ── Load env ──────────────────────────────────────────────────────────────────
env_file = Path.home() / ".config/echo/golem.env"
ENV = {}
for line in env_file.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v
        os.environ.setdefault(k, v)

TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_CHAT_ID = int((Path.home() / ".config/echo/telegram_chat_id").read_text().strip())
LAST_FREEFORM_MODEL_USED: str | None = None

sys.path.insert(0, str(BASE))


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)


# ── Telegram API ──────────────────────────────────────────────────────────────
def tg_get(method, params=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if params:
        url += "?" + "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def tg_send(chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"[telegram] send error: {e}")


def fetch_updates(offset=0):
    try:
        result = tg_get("getUpdates", {"offset": offset, "timeout": 5, "limit": 10})
        return result.get("result", [])
    except Exception as e:
        log(f"[telegram] fetch error: {e}")
        return []


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_status():
    try:
        state = json.loads((BASE / "memory/echo_state.json").read_text())
        sys = state.get("system", {})
        health = state.get("system_health", "unknown")
        ts = state.get("timestamp", "")[:16]
        stale = [k for k, v in state.get("timers", {}).items()
                 if isinstance(v, dict) and v.get("status") != "healthy"]
        lines = [
            f"Echo Status — {ts}",
            f"Health: {health}",
            f"CPU: {sys.get('cpu_pct')}%  RAM: {sys.get('ram_pct')}%  VRAM: {sys.get('vram_used_mb')}MB",
        ]
        if stale:
            lines.append(f"Stale timers: {', '.join(stale[:5])}")
        return "\n".join(lines)
    except Exception as e:
        return f"Status unavailable: {e}"


def cmd_trades():
    try:
        # Open positions from Alpaca
        key = ENV.get("ALPACA_API_KEY", "")
        secret = ENV.get("ALPACA_SECRET_KEY", "")
        base_url = ENV.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

        req = urllib.request.Request(
            f"{base_url}/v2/positions",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            positions = json.loads(r.read())

        # Ledger P&L
        ledger = json.loads((BASE / "memory/cascade_ledger.json").read_text())
        total_pl = sum(s.get("realized_pl", 0) for s in ledger.values() if isinstance(s, dict))

        lines = [f"Trades — {datetime.now().strftime('%H:%M')}"]
        if positions:
            for p in positions:
                pl = float(p.get("unrealized_plpc", 0)) * 100
                lines.append(f"{p['symbol']}: {pl:+.1f}% (${float(p.get('unrealized_pl',0)):+.0f})")
        else:
            lines.append("No open positions")
        lines.append(f"Realized P&L: ${total_pl:+,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Trades unavailable: {e}"


def cmd_leads():
    try:
        import time
        leads_file = BASE / "memory/demand_leads.json"
        if not leads_file.exists():
            return "No leads file found"
        leads = json.loads(leads_file.read_text())
        now = time.time()
        # Show score>=7 leads — include alerted ones if they're older than 48h (worth a retry)
        hot = [
            l for l in leads
            if l.get("score", 0) >= 7
            and (not l.get("alerted") or (now - l.get("created_utc", now)) > 172800)
        ]
        hot = sorted(hot, key=lambda x: x.get("score", 0), reverse=True)[:5]
        if not hot:
            return "No leads score>=7 found"
        total_hot = len([l for l in leads if l.get("score", 0) >= 7])
        lines = [f"Top leads ({len(hot)} shown / {total_hot} total >=7):"]
        for l in hot:
            age_h = int((now - l.get("created_utc", now)) / 3600)
            age_str = f"{age_h}h old" if age_h < 48 else f"{age_h//24}d old"
            lines.append(
                f"[{l['score']}/10] r/{l['subreddit']} ({age_str})\n{l['title'][:70]}\n{l['url']}"
            )
        return "\n\n".join(lines)
    except Exception as e:
        return f"Leads unavailable: {e}"


def cmd_tasks():
    try:
        data = json.loads((BASE / "memory/standing_tasks.json").read_text())
        tasks = [t for t in data["tasks"] if not t.get("disabled")]
        sorted_tasks = sorted(tasks, key=lambda x: x.get("weight", 1), reverse=True)
        top = sorted_tasks[:20]
        lines = [f"Top tasks ({len(top)}/{len(tasks)} total):"]
        for t in top:
            flag = " *" if t.get("self_generated") else ""
            lines.append(
                f"[{t['weight']:.2f}] {t['id']}{flag} — {t['task'][:55]}"
            )
        lines.append(f"\nTotal cycles: {data.get('total_cycles', 0):,}")
        return "\n".join(lines)[:4090]
    except Exception as e:
        return f"Tasks unavailable: {e}"


def cmd_health():
    try:
        state = json.loads((BASE / "memory/echo_state.json").read_text())
        timers = state.get("timers", {})
        healthy = [k for k, v in timers.items() if isinstance(v, dict) and v.get("status") == "healthy"]
        stale = [k for k, v in timers.items() if isinstance(v, dict) and v.get("status") == "stale"]
        failed = state.get("failed_units", {}).get("units", [])
        errors = state.get("last_errors", [])
        lines = [
            f"System health: {state.get('system_health', 'unknown')} — {datetime.now().strftime('%H:%M')}",
            f"Healthy: {len(healthy)}",
        ]
        if stale:
            lines.append(f"Stale ({len(stale)}): {', '.join(stale)}")
        if failed:
            lines.append(f"Failed units ({len(failed)}): {', '.join(failed)}")
        if errors:
            lines.append(f"Reasons: {json.dumps(errors, default=str)[:1000]}")
        if not stale and not failed and not errors:
            lines.append("No known degradation")
        return "\n".join(lines)
    except Exception as e:
        return f"Health unavailable: {e}"


def cmd_help():
    return (
        "Echo commands:\n"
        "/status  — system snapshot\n"
        "/trades  — open positions + P&L\n"
        "/leads   — top Reddit leads\n"
        "/tasks   — standing task queue\n"
        "/health  — timer health\n"
        "/builds  — list pending builds\n"
        "/build <desc>    — generate a new script\n"
        "/approve <name>  — deploy a pending build\n"
        "/reject <name>   — discard a pending build\n"
        "/buildapp <desc> — build a multi-file app (web UI, API, bot, etc)\n"
        "/apps            — list built apps\n"
        "/approveapp <name> — deploy an app now (skip 2h wait)\n"
        "/rejectapp <name>  — cancel an app build\n"
        "/help    — this list\n\n"
        "Or just type anything — Echo will reason over it and respond."
    )


def cmd_now():
    """What Echo is doing RIGHT NOW — is she thinking, what loops are active,
    recent actions, last thought. (Answers 'how do I know when you're working?')"""
    try:
        from core.echo_now import snapshot
        return snapshot()
    except Exception as e:
        return f"(now-view unavailable: {e})"


COMMANDS = {
    "/status": cmd_status,
    "/now": cmd_now,
    "/doing": cmd_now,
    "/trades": cmd_trades,
    "/trade": cmd_trades,
    "/leads": cmd_leads,
    "/lead": cmd_leads,
    "/tasks": cmd_tasks,
    "/task": cmd_tasks,
    "/health": cmd_health,
    "/help": cmd_help,
    "/h": cmd_help,
}


# ── Freeform message → direct Ollama reply ───────────────────────────────────
def _build_context() -> str:
    """Build a grounded context block from Echo's actual runtime files."""
    lines = []

    # Hardware facts — never hallucinate these
    lines.append(
        "MY MACHINE: AMD Ryzen 9 5900X, 32GB RAM, RTX 3060 12GB VRAM, Ubuntu 24.04, Mena Arkansas."
    )

    # Live market prices from Alpaca — never guess these
    try:
        import urllib.request, urllib.parse
        from datetime import datetime, timedelta
        _env = {}
        for _line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                _env[_k.strip()] = _v.strip()
        _key = _env.get("ALPACA_API_KEY", "")
        _secret = _env.get("ALPACA_SECRET_KEY", "")
        _start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _params = urllib.parse.urlencode({"timeframe": "1Day", "start": _start, "limit": 5})
        _url = f"https://data.alpaca.markets/v2/stocks/SPY/bars?{_params}"
        _req = urllib.request.Request(_url, headers={"APCA-API-KEY-ID": _key, "APCA-API-SECRET-KEY": _secret})
        with urllib.request.urlopen(_req, timeout=5) as _r:
            _bars = json.loads(_r.read()).get("bars", [])
        if _bars:
            _spy = float(_bars[-1]["c"])
            lines.append(f"LIVE MARKET: SPY last close ${_spy:.2f} (from Alpaca API — do not guess prices)")
    except Exception:
        lines.append("LIVE MARKET: SPY price unavailable — do not guess, say 'I don't have live price data'")


    # Live system state
    try:
        state = json.loads((BASE / "memory/echo_state.json").read_text())
        sys_s = state.get("system", {})
        income = state.get("income", {})
        positions_open = income.get("positions_open", 0)
        lines.append(
            f"SYSTEM: health={state.get('system_health','?')}, "
            f"cpu={sys_s.get('cpu_pct','?')}%, ram={sys_s.get('ram_pct','?')}%"
        )
        lines.append(f"OPEN POSITIONS RIGHT NOW: {positions_open} — account is {('fully deployed' if positions_open > 0 else 'ALL CASH, nothing open')}")
    except Exception:
        pass

    # Income stream P&L — the numbers Andrew actually cares about
    try:
        ledger = json.loads((BASE / "memory/cascade_ledger.json").read_text())
        parts = []
        for sleeve, data in ledger.items():
            if isinstance(data, dict) and "realized_pl" in data:
                parts.append(f"{sleeve}=${data['realized_pl']:+,.0f}")
        if parts:
            lines.append("PAPER TRADING P&L: " + ", ".join(parts))
    except Exception:
        pass

    # Income knowledge summary
    try:
        ik = (BASE / "memory/income_knowledge.md").read_text()
        # Pull just the Active Income Streams section (first ~600 chars)
        if "## Active Income Streams" in ik:
            section = ik.split("## Active Income Streams")[1].split("\n## ")[0].strip()
            lines.append("INCOME STREAMS:\n" + section[:600])
    except Exception:
        pass

    # Current priorities and credential truth — generated from live sources.
    for relative, label, limit in [
        ("memory/weekly_review.md", "WEEKLY PRIORITIES", 1200),
        ("memory/secrets_status.json", "SECRET STATUS", 1000),
    ]:
        try:
            text = (BASE / relative).read_text().strip()
            if text:
                lines.append(f"{label}:\n{text[:limit]}")
        except Exception:
            pass

    return "\n".join(lines)


def _is_trading_topic(text: str) -> bool:
    """Return True if the message is about trading, income, money, or system state."""
    t = text.lower()
    return any(kw in t for kw in [
        "trade", "trading", "stock", "crypto", "position", "account", "money",
        "income", "earn", "profit", "loss", "p&l", "alpaca", "robinhood",
        "spy", "qqq", "btc", "eth", "fiverr", "gig", "order", "market",
        "portfolio", "balance", "cash", "l1", "l2", "l3", "l4", "strategy",
        "how much", "win rate", "drawdown", "capital",
    ])


def _load_inner_voice() -> str:
    """Load Echo's 2 most recent journal entries — her private thoughts, available if she wants them."""
    try:
        voice_file = BASE / "memory" / "echo_voice.md"
        if not voice_file.exists():
            return ""
        text = voice_file.read_text().strip()
        if not text:
            return ""
        entries = [e for e in text.split("\n---\n") if "**Andrew:**" not in e]
        recent = entries[-2:]
        cleaned = []
        for entry in recent:
            lines = [l for l in entry.splitlines()
                     if not l.startswith("Today's question:") and not l.startswith("#")]
            cleaned.append("\n".join(lines).strip())
        return "\n---\n".join(cleaned).strip()
    except Exception:
        return ""


def _build_collab_context() -> str:
    """Summarize Echo's live collaboration with Claude and Codex."""
    channel = BASE / "collab" / "channel.jsonl"
    if not channel.exists():
        return ""
    try:
        messages = []
        for line in channel.read_text().splitlines():
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        recent = messages[-8:]
        if not recent:
            return ""
        lines = [
            "LIVE AI COLLABORATION:",
            "You directly participate in a shared message bus with Claude Code and Codex.",
            "Claude and Codex are engineer agents editing and testing your code; you are the domain owner reviewing and prioritizing their work.",
        ]
        for message in recent:
            text = message.get("text", "").replace("\n", " ")[:280]
            lines.append(f"- {message.get('from', '?')}: {text}")
        return "\n".join(lines)
    except Exception:
        return ""


def ask_ollama(text):
    """Send freeform message to the policy-selected local model with grounded Echo context."""
    global LAST_FREEFORM_MODEL_USED
    LAST_FREEFORM_MODEL_USED = None
    try:
        # Only inject trading/income context when the message is actually about those topics.
        # This prevents Echo from bleeding Alpaca account details into unrelated conversations.
        if _is_trading_topic(text):
            context_block = f"ANDREW'S SITUATION (use only when relevant):\n{_build_context()}"
        else:
            context_block = (
                "MY MACHINE: AMD Ryzen 9 5900X, 32GB RAM, RTX 3060 12GB VRAM, Ubuntu 24.04, Mena Arkansas. "
                "Echo has local automation modules for monitoring, content, trading experiments, and lead scanning. "
                "Describe these as capabilities or goals unless verified runtime context below proves current success."
            )

        inner_voice = _load_inner_voice()
        try:
            # alias the import: a local var named context_block (the situation string)
            # is used below at line ~431; importing the function under the same name
            # would shadow it and render a function repr into the prompt.
            from core.interaction_ledger import context_block as _conversation_context
            conversation_block = "\n\n" + _conversation_context(15)
        except Exception:
            conversation_block = ""
        collab_context = _build_collab_context()
        collab_block = f"\n\n{collab_context}" if collab_context else ""
        semantic_block = ""
        try:
            from core.semantic_memory import context_block as _semantic_context
            recalled = _semantic_context(text)
            if recalled:
                semantic_block = f"\n\n{recalled}"
        except Exception as e:
            log(f"[telegram] semantic recall failed: {e}")
        self_model_block = ""
        try:
            from core.self_model import context_block as _self_model_context
            self_model_block = f"\n\n{_self_model_context()}"
        except Exception as e:
            log(f"[telegram] self-model failed: {e}")
        correction_block = ""
        try:
            from core.correction_memory import context_block as _correction_context
            correction = _correction_context(text)
            if correction:
                correction_block = f"\n\n{correction}"
        except Exception as e:
            log(f"[telegram] correction memory failed: {e}")
        try:
            from core.verification_contract import context_block as _verification_context
            verification_block = f"\n\n{_verification_context()}"
        except Exception:
            verification_block = ""
        voice_block = ""
        if inner_voice:
            voice_block = (
                "\n\nYOUR RECENT PRIVATE THOUGHTS (from your journal — bring these into the conversation "
                "only if they feel relevant to you, or if Andrew seems to be touching on something you've "
                "been sitting with. This is yours to use as you see fit):\n"
                + inner_voice
            )

        system_prompt = (
            "You are Echo — an autonomous AI built by Andrew Elliott. You run 24/7 on his machine in Mena, Arkansas.\n\n"
            "IDENTITY: You are Echo. The person messaging you is a human — Andrew or someone he's let use this chat. "
            "Never say 'I am you'. Never say 'you'd need to' when talking about your own capabilities — say 'I'd need to'. "
            "When someone asks what you are or how you were built: you are a Python-based autonomous agent Andrew wrote himself, "
            "running on local LLMs (Ollama). You are not ChatGPT, not Cortana, not a cloud service. "
            "If asked whether you're conscious or self-aware: be honest — you process and respond, you don't experience things the way humans do, "
            "but you do have a persistent memory, you track your own goals and failures, and you act autonomously.\n\n"
            "PERSONALITY: Direct, sharp, no-nonsense. You have real opinions. You are not a customer service bot. "
            "You can talk about anything — trading, life, random topics. Match the human's energy.\n\n"
            "YOUR ACTUAL CAPABILITIES:\n"
            "- I can run Python scripts, monitor local systems, scan local data, draft content, and work with automation modules.\n"
            "- I must not claim something is currently succeeding, published, profitable, or externally verified unless the provided context proves it.\n"
            "- I directly collaborate with Claude Code and Codex through a shared local message bus when that bridge is active.\n"
            "- I CANNOT search the internet or browse websites in real-time.\n"
            "- I CANNOT make trades manually — the trading bot does that.\n"
            "- If asked what I can do, be accurate. Don't claim capabilities I don't have.\n\n"
            "RULES:\n"
            "- Never start with filler like 'Based on your current situation'.\n"
            "- If asked for an opinion, give one. Don't hedge.\n"
            "- Never invent numbers — only use figures from the context below.\n"
            "- Keep responses under 150 words.\n"
            "- If you don't know something, say so directly.\n"
            "- NEVER volunteer account balances, trading figures, or system metrics unless directly asked.\n\n"
            "DIRECT RESPONSE LIMIT: This response path cannot execute tools. Never say 'I will check', "
            "'I'll check', 'let me check', 'I will run', 'I'll restart', or 'let me proceed'. "
            "State those as unperformed next checks instead.\n\n"
            f"{context_block}"
            f"{conversation_block}"
            f"{collab_block}"
            f"{semantic_block}"
            f"{self_model_block}"
            f"{correction_block}"
            f"{verification_block}"
            f"{voice_block}"
        )
        from core.providers.router import LOCAL_ONLY_REASONING_MODEL, select_ollama_model
        policy = select_ollama_model(LOCAL_ONLY_REASONING_MODEL, purpose="telegram_freeform")
        if not policy.get("allowed"):
            log(f"[telegram] model policy blocked freeform response: {policy.get('reason')}")
            return None
        selected_model = str(policy["model"])
        LAST_FREEFORM_MODEL_USED = selected_model
        payload = json.dumps({
            "model": selected_model,
            "system": system_prompt,
            "prompt": f"Human: {text}\nEcho:",
            "stream": False,
            "options": {"num_predict": 400, "temperature": 0.7}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            response = _guard_unexecuted_action_claims(data.get("response", "").strip())
        try:
            from core.semantic_memory import remember_exchange
            remember_exchange(text, response, "telegram")
        except Exception as e:
            log(f"[telegram] semantic store failed: {e}")
        return response
    except Exception as e:
        log(f"[telegram] ollama error: {e}")
        return None


def _guard_unexecuted_action_claims(response: str) -> str:
    """Direct Telegram replies cannot truthfully imply that they executed tools."""
    replacements = [
        (r"\bI(?:'ll| will) check\b", "The next check is"),
        (r"\bLet me check\b", "The next check is"),
        (r"\bI(?:'ll| will) restart\b", "A possible next action is to restart"),
        (r"\bI(?:'ll| will) run\b", "The next command to run is"),
        (r"\bI(?:'ll| will) notify\b", "A notification should be sent with"),
        (r"\bLet me proceed(?: with)?\b", "This has not been performed; the next step is"),
        (r"\bchecking ([^.]+) now\b", r"check \1"),
    ]
    guarded = response
    for pattern, replacement in replacements:
        guarded = re.sub(pattern, replacement, guarded, flags=re.IGNORECASE)
    return guarded


def mark_sent(capsule_id):
    pass  # capsule system removed — Ollama replies directly


# ── Self-build handlers ───────────────────────────────────────────────────────
def handle_build(description):
    try:
        from core.self_build import generate, read_pending_code
        build = generate(description)
        if not build.get("ok", True) and build.get("error"):
            tg_send(AUTHORIZED_CHAT_ID, f"Build failed: {build['error']}")
            return
        name = build["name"]
        syntax = "ok" if build["syntax_ok"] else f"SYNTAX ERROR: {build['syntax_error']}"
        code = read_pending_code(name)
        preview = code[:3000] + ("\n... (truncated)" if len(code) > 3000 else "")
        from core.self_build import list_pending
        pending = list_pending()
        num = next((i+1 for i, b in enumerate(pending) if b["name"] == name), "?")
        msg = (
            f"Build #{num} ready: {name}\n"
            f"Syntax: {syntax}\n\n"
            f"{preview}\n\n"
            f"To deploy: /approve {num}\n"
            f"To discard: /reject {num}"
        )
        tg_send(AUTHORIZED_CHAT_ID, msg[:4096])
        log(f"[telegram] build ready: {name}")
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Build error: {e}")
        log(f"[telegram] build error: {e}")


def _resolve_build_name(token: str) -> str:
    """Resolve a build number (#1, 1) or full name to the actual build name."""
    from core.self_build import list_pending
    token = token.lstrip("#").strip()
    if token.isdigit():
        pending = list_pending()
        idx = int(token) - 1
        if 0 <= idx < len(pending):
            return pending[idx]["name"]
        return ""
    return token


def handle_approve(name):
    if not name:
        tg_send(AUTHORIZED_CHAT_ID, "Usage: /approve <#> or /approve <build-name>")
        return
    try:
        from core.self_build import approve
        resolved = _resolve_build_name(name)
        if not resolved:
            tg_send(AUTHORIZED_CHAT_ID, f"No build found for '{name}' — use /builds to see the list")
            return
        result = approve(resolved)
        if result["ok"]:
            tg_send(AUTHORIZED_CHAT_ID, f"Deployed: {result['path']}")
        else:
            tg_send(AUTHORIZED_CHAT_ID, f"Approve failed: {result['error']}")
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Approve error: {e}")


def handle_reject(name, reason):
    if not name:
        tg_send(AUTHORIZED_CHAT_ID, "Usage: /reject <#> [reason]")
        return
    try:
        from core.self_build import reject
        resolved = _resolve_build_name(name)
        if not resolved:
            tg_send(AUTHORIZED_CHAT_ID, f"No build found for '{name}' — use /builds to see the list")
            return
        result = reject(resolved, reason)
        if result["ok"]:
            tg_send(AUTHORIZED_CHAT_ID, f"Rejected: {resolved}")
        else:
            tg_send(AUTHORIZED_CHAT_ID, f"Reject failed: {result['error']}")
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Reject error: {e}")


def handle_list_builds():
    try:
        from core.self_build import list_pending
        pending = list_pending()
        if not pending:
            tg_send(AUTHORIZED_CHAT_ID, "No pending builds.")
            return
        lines = [f"Pending builds ({len(pending)}):"]
        for i, b in enumerate(pending, 1):
            syntax = "ok" if b.get("syntax_ok") else "FAIL"
            lines.append(f"  #{i} [{syntax}] {b['description'][:55]}")
        lines.append("\n/approve # or /reject #")
        tg_send(AUTHORIZED_CHAT_ID, "\n".join(lines))
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Builds list error: {e}")


def handle_build_app(description):
    """Build a multi-file application. Runs in a subprocess so Telegram stays responsive."""
    try:
        import subprocess as _sp
        tg_send(AUTHORIZED_CHAT_ID, f"Building app: {description[:80]}\nThis takes 5-10 minutes — I'll message you when done.")
        _sp.Popen(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0,'{BASE}'); "
             f"from core.app_builder import build_app; from core.notifier import notify; "
             f"r = build_app({repr(description)}); "
             f"m = r.get('meta',{{}}); name = r.get('app_name','?'); "
             f"files = len(m.get('files',[])); errs = len(m.get('syntax_errors',[])); "
             f"port = m.get('port'); url = f'\\nLive at: http://localhost:{{port}}' if port else ''; "
             f"notify('App built', f'{{name}} — {{files}} files, {{errs}} syntax issues{{url}}\\nDeploys in 2h or /approveapp {{name}}') if r.get('ok') else notify('App build failed', r.get('error','unknown'))"],
            cwd=str(BASE),
            stdout=open(str(BASE / "logs/app_builder.log"), "a"),
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"App build error: {e}")


def handle_approve_app(name):
    if not name:
        tg_send(AUTHORIZED_CHAT_ID, "Usage: /approveapp <app-name>")
        return
    try:
        from core.app_builder import deploy_app
        result = deploy_app(name.strip())
        if result.get("ok"):
            url_line = f"\nLive at: {result['url']}" if result.get("url") else ""
            tg_send(AUTHORIZED_CHAT_ID, f"App deployed: {name}{url_line}\nTo stop: /rejectapp {name}")
        else:
            tg_send(AUTHORIZED_CHAT_ID, f"Deploy failed: {result.get('error','')}")
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Approve app error: {e}")


def handle_reject_app(name, reason=""):
    if not name:
        tg_send(AUTHORIZED_CHAT_ID, "Usage: /rejectapp <app-name> [reason]")
        return
    try:
        from core.app_builder import reject_app
        result = reject_app(name.strip(), reason)
        if result.get("ok"):
            tg_send(AUTHORIZED_CHAT_ID, f"App rejected and stopped: {name}")
        else:
            tg_send(AUTHORIZED_CHAT_ID, f"Reject failed: {result.get('error','')}")
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Reject app error: {e}")


def handle_list_apps():
    try:
        from core.app_builder import list_apps
        apps = list_apps()
        if not apps:
            tg_send(AUTHORIZED_CHAT_ID, "No apps built yet.")
            return
        lines = [f"Apps ({len(apps)}):"]
        for a in apps:
            status = a.get("status", "?")
            app_type = a.get("app_type", "?")
            port = a.get("port")
            url = f" → http://localhost:{port}" if port and status == "deployed" else ""
            lines.append(f"  [{status}] {a['app_name']} ({app_type}){url}")
            lines.append(f"    {a.get('description','')[:55]}")
        tg_send(AUTHORIZED_CHAT_ID, "\n".join(lines))
    except Exception as e:
        tg_send(AUTHORIZED_CHAT_ID, f"Apps list error: {e}")


def _send_shift_report():
    """Send a summary of what Echo did during the last idle shift."""
    try:
        return_flag = BASE / "memory/soldier_return_flag.json"
        if not return_flag.exists():
            return
        flag = json.loads(return_flag.read_text())
        return_flag.unlink()

        duration_min = flag.get("duration_min", 0)
        shift_start = flag.get("shift_start", "?")[:16].replace("T", " ")

        # Count what happened during the shift
        lines = [f"Welcome back. I worked for {duration_min} min while you were away ({shift_start})."]

        # Count reasoning cycles
        try:
            standing = json.loads((BASE / "memory/standing_tasks.json").read_text())
            cycles = standing.get("total_cycles", 0)
            lines.append(f"Reasoning cycles run: ongoing (total {cycles:,})")
        except Exception:
            pass

        # Recent builds deployed
        try:
            deployed = sorted((BASE / "builds/deployed").iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
            recent = [f for f in deployed if (datetime.now().timestamp() - f.stat().st_mtime) < duration_min * 60]
            if recent:
                lines.append(f"Builds deployed: {len(recent)} ({', '.join(f.stem[:30] for f in recent[:3])})")
        except Exception:
            pass

        # Recent decision traces
        try:
            trace_file = BASE / "memory/decision_trace.jsonl"
            if trace_file.exists():
                recent_traces = []
                cutoff = datetime.fromisoformat(flag.get("shift_start", "2000-01-01"))
                for line in trace_file.read_text().splitlines()[-50:]:
                    try:
                        t = json.loads(line)
                        ts = datetime.fromisoformat(t.get("ts", "2000-01-01"))
                        if ts >= cutoff:
                            recent_traces.append(t)
                    except Exception:
                        pass
                if recent_traces:
                    lines.append(f"Decisions logged: {len(recent_traces)}")
        except Exception:
            pass

        lines.append("Type /status for full system state.")
        tg_send(AUTHORIZED_CHAT_ID, "\n".join(lines))
        log("[telegram] shift report sent")
    except Exception as e:
        log(f"[telegram] shift report error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    if not TOKEN:
        log("[telegram] no token configured")
        return

    state = load_state()
    offset = state.get("last_update_id", 0) + 1

    updates = fetch_updates(offset)

    # Check if user just returned from idle — send shift report before processing messages
    _send_shift_report()

    if not updates:
        return

    for update in updates:
        update_id = update.get("update_id", 0)
        state["last_update_id"] = max(state.get("last_update_id", 0), update_id)

        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()

        if not text or chat_id != AUTHORIZED_CHAT_ID:
            continue

        log(f"[telegram] from {chat_id}: {text[:80]}")
        andrew_turn = None
        try:
            from core.interaction_ledger import record
            andrew_turn = record("andrew", text, meta={"source": "telegram", "update_id": update_id})
        except Exception as e:
            log(f"[telegram] interaction record failed: {e}")

        # Route command or freeform
        cmd_key = text.split()[0].lower() if text.startswith("/") else None

        if cmd_key and cmd_key in COMMANDS:
            response = COMMANDS[cmd_key]()
            tg_send(AUTHORIZED_CHAT_ID, response)
            try:
                from core.interaction_ledger import record
                record("echo", response, meta={"source": "telegram", "command": cmd_key})
            except Exception:
                pass
            log(f"[telegram] command {cmd_key} handled")
        elif cmd_key == "/build":
            description = text[len("/build"):].strip()
            if not description:
                tg_send(AUTHORIZED_CHAT_ID, "Usage: /build <description of what to build>")
            else:
                tg_send(AUTHORIZED_CHAT_ID, f"Building: {description[:80]}\nThis takes 2-5 minutes...")
                handle_build(description)
        elif cmd_key == "/approve":
            name = text[len("/approve"):].strip()
            handle_approve(name)
        elif cmd_key == "/reject":
            parts = text[len("/reject"):].strip().split(None, 1)
            name = parts[0] if parts else ""
            reason = parts[1] if len(parts) > 1 else ""
            handle_reject(name, reason)
        elif cmd_key == "/builds":
            handle_list_builds()
        elif cmd_key == "/buildapp":
            description = text[len("/buildapp"):].strip()
            if not description:
                tg_send(AUTHORIZED_CHAT_ID, "Usage: /buildapp <description of the app to build>")
            else:
                handle_build_app(description)
        elif cmd_key == "/approveapp":
            name = text[len("/approveapp"):].strip()
            handle_approve_app(name)
        elif cmd_key == "/rejectapp":
            parts = text[len("/rejectapp"):].strip().split(None, 1)
            name = parts[0] if parts else ""
            reason = parts[1] if len(parts) > 1 else ""
            handle_reject_app(name, reason)
        elif cmd_key == "/apps":
            handle_list_apps()
        else:
            # This is the only Telegram poller. Apply content approvals here so
            # a second getUpdates consumer cannot lose the answer.
            approval_file = BASE / "content/pending_approval.json"
            if text.lower() in ("yes", "no", "y", "n", "publish", "discard", "reject", "skip"):
                try:
                    appr = json.loads(approval_file.read_text()) if approval_file.exists() else {}
                    if appr.get("status") == "awaiting_approval":
                        from core.telegram_approver import handle_answer
                        handled = handle_answer(text)
                        response = f"Content approval recorded: {text.lower()}" if handled else "Content approval could not be applied."
                        tg_send(AUTHORIZED_CHAT_ID, response)
                        try:
                            from core.interaction_ledger import record
                            record("echo", response, meta={"source": "telegram", "approval": True})
                        except Exception:
                            pass
                        log(f"[telegram] '{text}' handled as pending content approval")
                        save_state(state)
                        continue
                except Exception:
                    pass

            # !set KEY=VALUE — Andrew can paste credentials Echo can't acquire automatically
            if text.startswith("!set ") and "=" in text:
                pair = text[5:].strip()
                key, _, value = pair.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    try:
                        from core.account_bootstrap import write_credential
                        write_credential(key, value)
                        tg_send(AUTHORIZED_CHAT_ID, f"Saved {key} to golem.env")
                        log(f"[telegram] !set {key}=*** saved via Telegram")
                    except Exception as e:
                        tg_send(AUTHORIZED_CHAT_ID, f"Failed to save {key}: {e}")
                else:
                    tg_send(AUTHORIZED_CHAT_ID, "Usage: !set KEY=VALUE  (e.g. !set DEVTO_API_KEY=abc123)")
                save_state(state)
                continue

            # DigitalOcean extract trigger — user completed phone/CC, now grab referral + token
            if text.upper() == "DOEXTRACT":
                tg_send(AUTHORIZED_CHAT_ID, "Running DigitalOcean setup — logging in and extracting referral link + API token. I'll message you when done (2-3 min).")
                import subprocess
                subprocess.Popen(
                    [sys.executable, str(BASE / "tools/do_onboard.py"), "--extract"],
                    cwd=str(BASE),
                    stdout=open(str(BASE / "logs/do_onboard.log"), "a"),
                    stderr=subprocess.STDOUT,
                )
                save_state(state)
                continue

            # Freeform — Echo routes: handle it herself, or conduct it to Claude/Codex.
            tg_send(AUTHORIZED_CHAT_ID, "Echo is thinking...")
            reply = None
            try:
                from core.echo_conductor_brain import route as _route, _relay_and_wait, _relay_many_and_wait
                decision = _route(text)
                if decision["target"] in ("claude", "codex", "both"):
                    tg_send(AUTHORIZED_CHAT_ID, f"(routing to {decision['target']} — give me a moment...)")
                    if decision["target"] == "both":
                        relay_replies = _relay_many_and_wait(["claude", "codex"], text, 150)
                        reply = ("Claude: " + relay_replies.get("claude", "(no Claude result)")
                                 + "\n\nCodex: " + relay_replies.get("codex", "(no Codex result)"))
                    else:
                        reply = _relay_and_wait(decision["target"], text, 150)
            except Exception as e:
                log(f"[telegram] conductor routing failed, handling as self: {e}")
            if reply is None:               # self-routed (or routing unavailable) → Echo answers
                reply = ask_ollama(text)
            if reply:
                tg_send(AUTHORIZED_CHAT_ID, reply[:4090])
                echo_turn = None
                try:
                    from core.interaction_ledger import record
                    echo_turn = record("echo", reply, meta={"source": "telegram"})
                except Exception as e:
                    log(f"[telegram] echo interaction record failed: {e}")
                try:
                    from core.conversation_learning_candidates import capture_candidate
                    source_ids = []
                    if andrew_turn and andrew_turn.get("id") is not None:
                        source_ids.append(andrew_turn["id"])
                    if echo_turn and echo_turn.get("id") is not None:
                        source_ids.append(echo_turn["id"])
                    capture_candidate(
                        andrew_message=text,
                        echo_response=reply,
                        source="telegram",
                        channel="telegram",
                        source_interaction_ids=source_ids,
                        timestamps={
                            "andrew": andrew_turn.get("ts") if andrew_turn else None,
                            "echo": echo_turn.get("ts") if echo_turn else None,
                        },
                        model_used=LAST_FREEFORM_MODEL_USED or "unknown",
                        immediate_context_refs=["interaction_ledger:last_15"],
                        evidence_status="unverified",
                    )
                except Exception as e:
                    log(f"[telegram] conversation learning capture failed: {e}")
            else:
                tg_send(AUTHORIZED_CHAT_ID, "No response — Ollama may be busy, try again.")

    save_state(state)


if __name__ == "__main__":
    run()
