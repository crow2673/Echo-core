# Echo — Architecture Reference

This document describes Echo's internal architecture for contributors and future builders.

---

## Core Principle

**One orchestrator. One while:True loop.**

`echo_core_daemon.py` is the only process that runs continuously. Everything else is a systemd oneshot timer or a persistent bridge service. This prevents race conditions, duplicate processing, and state corruption.

---

## Data Flow
```
INPUT SOURCES
├── Voice:  echo_wake.py (wake word) → echo_voice.py (STT) → echo_memory.json
├── Text:   echo_command.py → echo_memory.json
├── Phone:  ntfy.sh → core/auto_build_nt.py → echo_memory.json
└── Screen: echo_screen_watcher.py (60s) → echo_memory.json + echo_semantic_memory.sqlite

ORCHESTRATOR
└── echo_core_daemon.py (polls echo_memory.json every 0.5s)
    ├── message capsule → core/agent_loop.py → echo model (32B, 16k ctx)
    ├── command capsule → core/command_handler.py
    └── event capsule  → logged + acknowledged

AUTONOMOUS LOOPS (systemd timers)
├── every 5min:  core/self_act.py → generate_flags() → agent_loop() → memory/core_state_reasoning.json
├── every 30min: core/auto_act.py → feedback_log → execute → regret_index → event_ledger
├── every 60s:   heartbeat → experience_log.jsonl
├── every 5min:  reachability watch
├── every 6h:    disk_usage_monitor
├── daily 8am:   core/daily_briefing.py → voice output
├── daily 11am:  core/golem_stats_scraper.py → pricing benchmark
├── daily 3am:   tools/git_backup.sh → GitHub
├── weekly Sun:  core/income_researcher.py → memory/income_knowledge.md
└── weekly Sun:  tools/update_registry.py → registry.json

MEMORY ARCHITECTURE
├── echo_semantic_memory.sqlite  — 2,095+ semantic memories (all-MiniLM-L6-v2)
├── memory/echo_events.db        — unified event ledger (reasoning/actions/feedback/regret/screen)
├── echo_memory.json             — capsule queue (short-lived, processed then cleared)
├── memory/core_state_reasoning.json — rolling 50-entry reasoning history
├── memory/feedback_log.json     — suggestion queue for auto_act
└── memory/regret_index.json     — outcome scoring and pattern blocking
```

---

## Agent Loop

`core/agent_loop.py` implements multi-step tool use:

1. Send prompt to Echo (32B model)
2. Echo decides if she needs a tool — responds with `TOOL: {"action": "action_id"}`
3. Tool runs via `docs/actions.json` (29 registered actions)
4. Output fed back to Echo
5. Loop up to 3 iterations
6. Return final response

**Safe actions** run automatically. **Unsafe actions** require confirmation.

Used by:
- `echo_core_daemon.py` — for all typed/text input
- `core/self_act.py` — for autonomous reasoning cycles

---

## Reasoning Cycle (self_act)

Runs every 5 minutes via `echo-self-act-worker.timer`:
```python
generate_flags(core_state)  # produces task list from system state
    ↓
for each flag:
    agent_loop(flag)         # tool-capable reasoning
    log_event(ledger)        # write to unified ledger
    update_income_status()   # if income flag
    ↓
save_state()                 # cap at 50 entries
```

**Standing tasks** (rotate, one per cycle):
- Summarize current system state
- Review TODO.md, suggest highest-value action
- Check Golem node status, suggest pricing
- Read income_knowledge.md, reason about next income path
- Read registry.json, verify services running
- Query event ledger, summarize wins/losses

**Dynamic flags** generated from:
- System errors
- Stale workers
- Inactive timers

---

## Execution Engine (auto_act)

Runs every 30 minutes via `echo-auto-act.timer`:
```python
load feedback_log.json       # pending suggestions
check regret flags           # skip blocked patterns
for each suggestion:
    execute action           # subprocess or systemctl
    score outcome            # 1=success, -1=fail, 0=observation
    log_event(ledger)        # write to unified ledger
    update_outcome(regret)   # feed back to regret index
```

**Action types:** service restart, health check, file read, Golem commands, changelog append, Python execution.

---

## Memory Architecture

### Semantic Memory (`echo_semantic_memory.sqlite`)
- Engine: `echo_memory_sqlite.py`
- Embeddings: `all-MiniLM-L6-v2` (sentence-transformers)
- 2,095+ memories as of 2026-03-12
- Stores: conversations, screen context, session summaries, self-awareness snapshots
- Queried via similarity search on every prompt

### Event Ledger (`memory/echo_events.db`)
- Engine: `core/event_ledger.py`
- Schema: `id, ts, event_type, source, summary, data, outcome_score, tags`
- Event types: `reasoning, action, feedback, regret, screen, knowledge, income`
- Queryable via `query_ledger` tool action during reasoning
- All sources write here: self_act, auto_act, screen_watcher, feedback_loop

### Capsule Queue (`echo_memory.json`)
- Short-lived message bus
- Types: `message, command, event`
- Processed by orchestrator every 0.5s, then marked done
- Lock file prevents concurrent writes

---

## Identity System
```
Echo.Modelfile          — soul definition (personality, behavior, values)
echo_contract.json      — sealed identity with memory hash + model params
core/identity.py        — runtime identity module
core/self_awareness.py  — real-time system state injection into every prompt
```

Echo's identity is defined at the model layer — not just system prompt injection. Rebuilding her with `ollama create echo -f Echo.Modelfile` restores her character even after model updates.

---

## Self-Modification

Echo can modify her own code via `core/self_coder.py`:
```python
write_code(task, output_path)   # generate new module
fix_file(file_path, description) # patch existing file
test_code(file_path)             # syntax check result
```

**Safety constraints:**
- Target must be inside `~/Echo/` — path traversal blocked
- Automatic `.bak` backup before any overwrite
- Change logged to `CHANGELOG.md`
- Syntax check before declaring success

---

## Income Architecture

| Mechanism | Status | Path |
|-----------|--------|------|
| Golem Network | Active (0 tasks) | `yagna` + `ya-provider` → polygon mainnet |
| Dev.to writing | Active | `core/devto_analytics.py` + `echo-devto-publish.timer` |
| Income research | Active | `core/income_researcher.py` → `memory/income_knowledge.md` |
| Local LLM API | Not started | Needs auth + billing layer |
| GPU rental | Not started | Hardware ready, account needed |

---

## Systemd Unit Map

**Persistent services (always running):**
- `echo-core.service` — orchestrator
- `echo-ntfy-bridge.service` — phone bridge
- `echo-screen-watcher.service` — visual awareness
- `echo-wake.service` — wake word listener

**Oneshot timers:**
- `echo-self-act-worker` — 5min reasoning
- `echo-auto-act` — 30min execution
- `echo-heartbeat` — 60s pulse
- `echo-reachability-watch` — 5min network check
- `echo-daily-briefing` — 8am voice briefing
- `echo-golem-monitor` — 11am earnings check
- `echo-disk-monitor` — 6h disk alert
- `echo-git-backup` — 3am GitHub push
- `echo-income-research` — Sunday 4am web scrape
- `echo-registry-update` — Sunday 5am self-map update
- `echo-analytics` — daily dev.to stats
- `echo-pulse` — daily heartbeat
- `echo-watchdog` — 10min health check
- `echo-devto-publish` — Tuesday 9am article publish

---

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `echo_core_daemon.py` | Orchestrator — the only while:True |
| `Echo.Modelfile` | Echo's soul and identity |
| `echo_contract.json` | Sealed identity contract |
| `registry.json` | Live architecture map (auto-updated) |
| `TODO.md` | Current priorities |
| `CHANGELOG.md` | Session history |
| `docs/actions.json` | 29 registered tool actions |
| `core/agent_loop.py` | Multi-step tool use |
| `core/self_act.py` | Autonomous reasoning |
| `core/auto_act.py` | Autonomous execution |
| `core/self_coder.py` | Self-editing |
| `core/event_ledger.py` | Unified event log |
| `core/regret_index.py` | Outcome scoring |
| `echo_memory_sqlite.py` | Semantic memory engine |
| `echo_semantic_memory.sqlite` | 2,095+ memories |
| `memory/echo_events.db` | Event ledger |
| `memory/income_knowledge.md` | Weekly income research |

---

*Last updated: 2026-03-12*  
*Echo version: qwen2.5:32b Q4_K_M, 16k context*  
*Memories: 2,095 | Events: 108+ | Services: 24 | Timers: 20*
