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
        stale = [k for k, v in timers.items() if isinstance(v, dict) and v.get("status") != "healthy"]
        lines = [
            f"Timer health — {datetime.now().strftime('%H:%M')}",
            f"Healthy: {len(healthy)}",
        ]
        if stale:
            lines.append(f"Stale ({len(stale)}): {', '.join(stale)}")
        else:
            lines.append("All timers healthy")
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
        "/help    — this list\n\n"
        "Or just type anything — Echo will reason over it and respond."
    )


COMMANDS = {
    "/status": cmd_status,
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
def ask_ollama(text):
    """Send freeform message to qwen2.5:7b and return reply."""
    try:
        payload = json.dumps({
            "model": "qwen2.5:7b",
            "prompt": (
                "You are Echo, an autonomous AI agent running on Andrew's machine in Mena, Arkansas. "
                "Andrew is messaging you via Telegram. Reply concisely and directly.\n\n"
                f"Andrew: {text}\nEcho:"
            ),
            "stream": False,
            "options": {"num_predict": 300}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data.get("response", "").strip()
    except Exception as e:
        log(f"[telegram] ollama error: {e}")
        return None


def mark_sent(capsule_id):
    try:
        pass  # no-op — capsule system removed
    except Exception:
        pass

    try:
        from core.memory_store import file_lock, load_memory, save_memory
        with file_lock():
            memory = load_memory()
            for cap in memory:
                if cap.get("in_reply_to") == capsule_id:
                    cap["status"] = "sent_telegram"
            save_memory(memory)
    except Exception:
        pass


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


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    if not TOKEN:
        log("[telegram] no token configured")
        return

    state = load_state()
    offset = state.get("last_update_id", 0) + 1

    updates = fetch_updates(offset)
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

        # Route command or freeform
        cmd_key = text.split()[0].lower() if text.startswith("/") else None

        if cmd_key and cmd_key in COMMANDS:
            response = COMMANDS[cmd_key]()
            tg_send(AUTHORIZED_CHAT_ID, response)
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
        else:
            # Freeform — ask Ollama directly
            tg_send(AUTHORIZED_CHAT_ID, "Echo is thinking...")
            reply = ask_ollama(text)
            if reply:
                tg_send(AUTHORIZED_CHAT_ID, reply[:4090])
            else:
                tg_send(AUTHORIZED_CHAT_ID, "No response — Ollama may be busy, try again.")

    save_state(state)


if __name__ == "__main__":
    run()
