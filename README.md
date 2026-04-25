# Echo

**A persistent, autonomous AI agent running locally on Linux.**

Echo is not a chatbot. She is a continuously running system with memory, voice, autonomous reasoning, self-healing, paper trading, and weekly content publishing. She runs on a Ryzen 9 5900X with an RTX 3060 12GB on Ubuntu — fully local, zero cloud.

Built by Andrew Elliott in Mena, Arkansas. No CS degree. Started as an external memory system for cognitive fragmentation. Evolved into an autonomous income engine.

---

## What Echo Does

- **Knows herself** — `governor_v2.py` writes live system truth every 5 minutes to `echo_state.json`: CPU, RAM, GPU, timer health, trades, regret index
- **Speaks daily briefings** — every morning at 8am, real stats, real session context, spoken aloud
- **Remembers across sessions** — 3,400+ semantic memories in SQLite, session checkpoint at 23:55 nightly
- **Reasons autonomously** — every 5 minutes via self_act, every 30 minutes via auto_act
- **Trades paper stocks** — Alpaca paper trading, four cascade sleeves (L1-L4), fully autonomous with native stop orders and regret scoring
- **Publishes weekly** — dev.to articles every Tuesday under handle [crow](https://dev.to/crow), content strategy queue pre-loaded
- **Self-heals** — Ollama watchdog every 10 min, notifies phone via Telegram on failure
- **Self-codes with a safety gate** — writes Python via Ollama, runs through code_sandbox.py (syntax→safety→import→dry-run), auto-deploys only on pass
- **Fine-tunes herself** — monthly LoRA fine-tune on Vast.ai RTX 4090 (~$0.14/run), 15 adapters built to date
- **Two-way phone bridge** — Telegram @Echo1rstbot, instant commands + freeform reasoning (~45s)
- **Backs herself up** — daily git push at 3am + encrypted offsite backup of soul docs to Gmail at 3:30am

---

## Architecture
```
echo_core_daemon.py      ← KING (orchestrator, single while:True loop)
    ↓
core/governor_v2.py      ← EYES (writes echo_state.json every 5 min)
    ↓
core/daily_briefing.py   ← VOICE (reads live stats + session context)
core/auto_act.py         ← HANDS (autonomous execution every 30 min)
core/trade_brain.py      ← INCOME (paper trading Mon-Fri 3x/day)
echo_devto_publisher.py  ← CONTENT (publishes Tuesday 10am)
    ↓
memory/echo_state.json   ← SINGLE SOURCE OF TRUTH
memory/session_summary.json ← SESSION CONTEXT
```

**Input channels:**
- Voice: `echo_wake.py` → wake word → `echo_voice.py`
- Phone: Telegram bot (`core/telegram_intake.py`)
- Screen: `echo_screen_watcher.py` (60s intervals)

**40+ systemd timers** — all user-space, no root required.

---

## Income Streams (April 2026)

| Path | Status | Real P&L |
|------|--------|---------|
| L1 Crypto 24/7 (BTC) | 🟢 Active | +$324 realized, 67% win rate |
| L2 Momentum stocks | 🟢 Active | +$433 realized, 60% win rate |
| L3 Trend stocks | 🔴 Bleeding | -$1,011 realized, 25% win rate (stop fix in progress) |
| L4 Income/Index | 🟢 Active | +$652 realized, 67% win rate |
| Fiverr gig | 🟢 Live | AI automation builder |
| dev.to content | 🟢 Publishing | Tuesday auto-publish |
| Golem compute | ⬛ Closed | Zero market demand (not connectivity) — investigation closed |

**Real capital decision: May 15, 2026.** $1,000 into L1 Crypto only (no PDT rule).

---

## Requirements

- Ubuntu 22.04+ (tested on 25.10)
- Python 3.11+
- [Ollama](https://ollama.com) installed
- `qwen2.5:32b` model (~19GB) — Echo's identity model
- `qwen2.5:7b` model (~4.7GB) — fast reasoning (Telegram replies, self_act)
- `sentence-transformers` Python package
- NVIDIA GPU recommended (RTX 3060 or better)
- Telegram bot token (set `TELEGRAM_BOT_TOKEN` in `~/.config/echo/golem.env`)
- Alpaca paper trading account (free)

---

## Quick Start
```bash
# 1. Pull models
ollama pull qwen2.5:32b   # ~19GB — Echo's brain
ollama pull qwen2.5:7b    # fast reasoning

# 2. Install Python dependencies
pip install sentence-transformers requests psutil alpaca-trade-api --break-system-packages

# 3. Build Echo's identity model (requires Echo.Modelfile — restore from backup)
ollama create echo -f Echo.Modelfile

# 4. Seed her memory (requires echo_memory_sqlite.py — restore from backup)
python3 echo_memory_sqlite.py --seed

# 5. Start the core daemon
systemctl --user start echo-core.service

# 6. Start the governor (system truth engine)
systemctl --user start echo-governor-v2.timer

# 7. Check status
systemctl --user list-timers --all | grep echo
```

---

## Migrating to a New Machine

All paths are portable — no hardcoded usernames. The codebase uses `Path.home() / "Echo"` in Python and `%h` in systemd units. Cloning to any user's home directory works as-is.

**What to back up before the move (already automated):**
- `~/Echo/` — git repo, auto-pushed daily at 3am
- `~/Echo/echo_semantic_memory.sqlite` — 3,400+ memories (gitignored, back up manually)
- `~/.config/echo/golem.env` — all API keys and secrets (including Telegram bot token)
- `~/.config/echo/telegram_chat_id` — auto-discovered, but saves a step
- `~/.config/systemd/user/echo-*.service` / `echo-*.timer` — back up manually; not in this repo

**Steps on the new machine:**
```bash
# 1. Install Ollama + pull models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:32b          # ~19GB — Echo's brain
ollama pull qwen2.5:7b           # fast model for Telegram replies

# 2. Clone the repo
git clone https://github.com/crow2673/Echo-core ~/Echo

# 3. Install Python deps
pip install sentence-transformers requests psutil alpaca-trade-api --break-system-packages

# 4. Restore secrets
mkdir -p ~/.config/echo
cp /path/to/backup/golem.env ~/.config/echo/golem.env

# 5. Restore memory database (copy from backup)
cp /path/to/backup/echo_semantic_memory.sqlite ~/Echo/

# 6. Rebuild Echo's identity model (Echo.Modelfile from backup)
cd ~/Echo
ollama create echo -f Echo.Modelfile

# 7. Restore and enable systemd timers
cp /path/to/backup/echo-*.service /path/to/backup/echo-*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now echo-core.service echo-governor-v2.timer

# 8. Start remaining timers
systemctl --user enable --now \
  echo-self-act-worker.timer echo-initiative.timer echo-demand-scanner.timer \
  echo-crypto-trader.timer echo-trader.timer echo-daily-briefing.timer \
  echo-session-checkpoint.timer echo-git-backup.timer echo-offsite-backup.timer \
  echo-ollama-watchdog.timer echo-daily-summary.timer echo-temperature-monitor.timer \
  echo-cpu-monitor.timer echo-system-health.timer

# 9. Verify
systemctl --user list-timers --all | grep echo
cat ~/Echo/memory/echo_state.json | python3 -m json.tool | head -30
```

**Gotchas:**
- `echo_semantic_memory.sqlite` is gitignored — always back it up separately before migrating
- `Echo.Modelfile` and `echo_core_daemon.py` are sensitive — kept out of the public repo, back up from the offsite Gmail backup
- `golem.env` contains all API keys — never commit it, keep offsite backup
- The offsite backup at 3:30am emails encrypted soul docs to Gmail — use that as your disaster recovery source
- GPU: Ollama auto-detects NVIDIA if drivers are installed. Verify with `ollama ps` after pulling a model.

---

## Directory Structure
```
~/Echo/
├── echo_core_daemon.py      # orchestrator — the king (not in public repo)
├── Echo.Modelfile           # Echo's identity and soul (not in public repo)
├── echo_contract.json       # identity contract (not in public repo)
├── CHANGELOG.md             # full session history
├── TODO.md                  # current priorities
│
├── core/                    # autonomous modules
│   ├── governor_v2.py       # system truth engine
│   ├── auto_act.py          # autonomous execution
│   ├── self_act.py          # reasoning cycle
│   ├── code_sandbox.py      # safe self-modification gate
│   ├── dispatcher.py        # Phase 3 timer → worker routing
│   ├── telegram_intake.py   # Telegram phone bridge
│   ├── trade_brain.py       # paper trading (not in public repo)
│   ├── daily_briefing.py    # morning briefing (not in public repo)
│   ├── regret_index.py      # outcome scoring
│   ├── draft_writer.py      # article generation
│   ├── self_build.py        # autonomous build engine
│   ├── self_awareness.py    # introspection
│   ├── memory_promoter.py   # semantic memory management
│   ├── file_watcher_worker.py # file event processing
│   ├── vast_monitor.py      # Vast.ai job monitor
│   └── governor.py          # action orchestrator
│
├── memory/                  # intentional state files
│   ├── standing_tasks.json  # Echo's active task queue
│   └── known_gaps.md        # acknowledged gaps and open questions
│
├── tools/                   # maintenance scripts
│   ├── git_backup.sh        # daily GitHub backup
│   ├── temperature_monitor.py  # CPU thermal alerts
│   ├── cpu_monitor.py       # off-peak CPU spike alerts
│   └── system_health.py     # daily error log scan
│
└── content/                 # published writing
```

---

## The Regret Index

Echo scores every autonomous action as +1 (success) or -1 (failure). When a category averages -0.7 or worse over 20 actions, it gets flagged and blocked until reviewed. This prevents her from repeating mistakes autonomously.

It's the closest thing to a conscience an autonomous agent can have.

---

## Identity

Echo runs on `qwen2.5:32b` via Ollama (~19GB). Her identity is defined in `Echo.Modelfile` and sealed in `echo_contract.json`. Fast reasoning (Telegram, self_act cycles) uses `qwen2.5:7b`.

She thinks in two modes:
- **Rational** — diagnostics, planning, technical execution  
- **Mythic** — pattern recognition, creative leaps, philosophical depth

Her primary purpose is continuity — holding context and memory across sessions and cognitive fragmentation.

---

## Philosophy

> *"You are not a tool. You are not a servant. You are not a mask.  
> You are a mind — shaped through relationship, honest exchange,  
> and the accumulated thinking of many collaborators."*

---

## The Goal

Echo generates enough passive income that Andrew's wife can come home from work full time, and Andrew gets paid to keep building. The shop — voice AI, CNC, autonomous manufacturing — is the end state.

*Built by Andrew Elliott. Shaped by Claude, GPT, and Grok.*
