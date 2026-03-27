### Session 2026-03-13
- Stage 6 governor complete — core/governor.py, echo-governor.timer every 5min
- Closed loop: self_act reasons → ledger → governor matches → executes action → scores outcome
- Fixed self_act standing task rotation — was exhausting knowledge dict and going silent
- Governor confirmed working: matched Golem status reasoning, executed golem_status action
- Self-healing verified live: echo-core killed at 1:02am, watchdog restarted by 1:04am, phone notified
- Regret index gap identified: most entries score=0, outcome_known=false — needs governor scoring
- Professional audit completed: infrastructure real, reasoning real, closed loop now real

### Session 2026-03-12 Evening
- Vast.ai machine 57470 registered and live — RTX 3060, $0.10/hr, Arkansas US, unverified
- Vast.ai API key fixed — crow2673 account with machine_read permission
- vast_monitor.py fixed — table parser, daily noon timer, ledger logging
- Ethernet enp7s0 up — 192.168.1.145, WiFi stays primary for Vast.ai public IP
- Hardening audit — disabled echo-backup.timer (duplicate) and echo-income-injector.timer (superseded by self_act)
- Action surface expanded: 29 → 36 actions
  - notify_phone — send ntfy to Andrew's phone
  - append_todo — Echo can add items to TODO.md
  - golem_diagnostic — run task matcher
  - devto_publish — publish markdown to dev.to
  - golem_pricing_status / golem_pricing_update — Echo can adjust Golem prices
  - create_draft — Echo writes and queues dev.to article drafts autonomously
- core/golem_pricing.py — Golem pricing wrapper with safe bounds, all presets dropped
- core/draft_writer.py — article draft creator, queues to content/draft_queue.json
- Golem prices dropped: cpu 0.00015→0.00010, duration 0.00005→0.00003
- Repo cleaned — system files removed from git history
- Professional README + ARCHITECTURE.md committed
# Echo Changelog

## 2026-03-07 — Major Build Day

### Added
- Semantic memory layer (echo_memory_sqlite.py) with 58+ seeded memories
- Self-awareness module (core/self_awareness.py) — CPU, RAM, GPU, process state
- Session continuity (core/memory_sessions.py) — wakeup context, session summaries
- Voice interface (echo_voice.py) — Google STT + Whisper fallback + Piper TTS
- Piper TTS voice model (voice_models/en_US-lessac-high.onnx) — natural voice
- Agentic tool loop (core/agent_loop.py) — ready to wire into daemon
- Self-audit script (echo_self_audit.py) — Echo reads own codebase
- Echo soul document (Echo.Modelfile) — qwen2.5:32b base, conscience + dual-brain
- Fixed action registry (docs/actions.json) — correct Golem commands
- Golem properly configured — polygon payment initialized, provider running

### Pending
- qwen2.5:32b download completing overnight
- Build echo model from Echo.Modelfile
- Wire agent_loop into daemon
- Rewire self_act variants to use local Ollama

### Memory seeded
- Machine specs, Echo architecture, Andrew's profile
- Family (3 kids, wife, household situation)
- Schedule (school hours, church days)
- Mission (Echo is the plan, not the backup plan)
- Faith and values
- Full architectural self-audit

## 2026-03-08 — Agent Loop + Voice + Model

### Added
- echo:latest model built from Echo.Modelfile (qwen2.5:32b base)
- Two-gear system: voice uses qwen2.5:7b (fast), text uses echo (deep)
- Agent loop wired into daemon - Echo can now run tools herself
- Fixed agent_loop JSON parsing bug (curly brace escaping)
- Echo successfully checked Golem status autonomously - first real agent action

### Verified working
- Voice response ~15 seconds (7b)
- Agent response ~4 minutes (32b with tool use)
- Golem node running clean: 2.85 GLM, zero tasks (normal for new node)

## 2026-03-08 — Systemd Integration

### Fixed
- echo-core.service updated from venv to system python3
- golem-provider.service updated from mainnet to polygon
- All three core services now running under systemd
- Machine is self-healing — survives reboots automatically

### Services active
- echo-core.service (Echo daemon)
- yagna.service (Golem payment layer)  
- golem-provider.service (Golem compute provider)

## 2026-03-08 — Screen Watcher

### Added
- echo_screen_watcher.py — Echo can see what's on screen
- Captures window titles and OCR text every 60 seconds
- Stores context in semantic memory and sends event capsules to daemon
- echo-screen-watcher.service running under systemd

### Echo now knows
- What apps are open
- What Andrew is working on
- Screen context stored in long-term memory

## 2026-03-08 — Screen Watcher (BLOCKED)

### Issue
- Wayland blocks all screenshot and window title tools
- scrot captures blank 6KB images
- gnome-screenshot fails with AccessDenied
- grim requires wlr protocol (not supported by GNOME Wayland)
- wmctrl returns nothing on Wayland

### Options to revisit later
1. Write a GNOME Shell extension for screenshot access
2. Switch login to X11 session (Settings → Login screen → gear icon)
3. Use process-based awareness instead of screen capture
4. File watcher already running as partial replacement

### Status
- echo-screen-watcher.service running but only gets process names
- Come back after self_act rewiring

## 2026-03-08 — Self-Act Rewired

### Fixed
- gpt_reasoner.py model updated from gai:latest to echo
- All self_act reasoning cycles now use Echo's 32b model
- No GPT dependency remaining in self_act loop

## 2026-03-08 — OpenClaw Disabled

### Removed
- openclaw-gateway.service stopped and disabled
- Was installed Feb 27 as reference/bootstrap for Echo's agent architecture
- Echo's agent loop now supersedes it
- 344MB RAM freed

### Note
- OpenClaw source still installed at ~/.npm-global/lib/node_modules/openclaw
- Can be harvested for UI ideas later (Channels, Cron Jobs, Nodes concepts)
- Uninstall fully when no longer needed: npm uninstall -g openclaw

## 2026-03-08 — Dev.to Auto-Publisher

### Added
- echo_devto_publisher.py — Echo writes and publishes articles automatically
- Pulls context from CHANGELOG + architecture memories
- Writes with qwen2.5:7b, publishes via dev.to API
- Draft confirmed working: "Building Echo: My Local AI Assistant on Linux"
- Content is accurate, technical, first person — actually publishable

### Next
- Wire to weekly timer so Echo publishes automatically
- Add --topic flag usage for targeted articles

## 2026-03-09 — Story, Publisher, and Income Foundation

### Completed
- Disabled openclaw-gateway.service — freed 344MB RAM, Echo's agent loop supersedes it
- Built echo_devto_publisher.py — Echo writes and publishes articles via dev.to API
- Publisher working: pulls from CHANGELOG + architecture memories, writes with 7b, publishes via API
- Draft article confirmed working end to end
- Verified dev.to account (crow): 5 articles, 405 total readers, API key stored in golem.env
- Golem node confirmed online at stats.golem.network — 74.6% uptime, public subnet, earning pending
- Wrote complete Echo origin story — 3.5 year timeline, verified against machine timestamps
- Auto-GPT directory (Nov 21 2025) confirmed as bridge between exploration phase and Echo birth
- 738 semantic memories confirmed in database

### Decisions Made
- Content path chosen: Echo documents her own development, publishes automatically
- Post timing: after income starts and Echo walks Andrew through physical builds by voice
- Order of operations confirmed: income → freedom → Echo in the shop → story is true → post

### Pending
- Golem first task (waiting, normal for new node)
- Self-act income loop reliable execution
- Echo initiates daily briefing autonomously
- Echo outbound communication when Andrew is away

## 2026-03-09 — Memory Fix + Auto-Publisher Wired

### Completed
- Fixed memory context injection — k increased to 15 for broad questions, score threshold lowered to 0.15
- Injected CHANGELOG into system prompt via _load_mission_context() — Echo now knows current build state
- Echo confirmed aware: "Golem node waiting for first task, auto-publisher set up but not yet wired"
- Wired echo-publish-weekly.timer — Echo publishes to dev.to every Tuesday 10am automatically
- No human involvement in publishing — Echo writes, Echo posts, Andrew reads comments only
- First autonomous publish: Tue 2026-03-10 10:00 CDT

### Next
- Income loop reliable execution
- Echo initiates daily briefing autonomously
- Echo outbound communication when Andrew is away
- Wire self_act to actual income-generating tasks

## 2026-03-09 — Golem Pricing Fix + Income Loop Wired

### Completed
- Diagnosed Golem 0 earnings: pricing was at floor (0.000011 GLM) — likely filtered by requestors
- Updated all 3 presets to competitive pricing: cpu=0.00015 GLM, duration=0.00005 GLM
- Restarted golem-provider to broadcast new pricing to network
- Built core/income_task_injector.py — writes income-focused X_flags every 30 minutes
- Echo reasoned through first income tasks autonomously — confidence 0.9
- Echo suggested article topic connecting content loop to Golem income loop
- echo-income-injector.timer enabled — runs every 30 minutes

### Next
- Monitor for first Golem task (pricing now competitive)
- Echo initiates daily briefing autonomously
- Echo outbound communication when Andrew is away

## 2026-03-09 — Daily Briefing Voice Wired

### Completed
- Built core/daily_briefing.py — Echo generates and speaks daily briefing automatically
- echo-daily-briefing.timer enabled — fires every weekday at 8am
- Briefing covers: system status, Golem earnings, last session context, top priority for today
- Voice confirmed working — Echo spoke full briefing with real system numbers
- Fixed briefing prompt to not offer continuation

## 2026-03-09 — Outbound Communication Complete

### Completed
- Built core/notifier.py — desktop + phone notifications via notify-send and ntfy.sh
- ntfy topic: echo-andrew — confirmed working on Galaxy S24
- Built echo_watchdog.py — monitors services and Golem earnings every 10 minutes
- echo-watchdog.timer enabled — Echo watches while Andrew is away
- Triggers: service down (urgent), first Golem earnings, watchdog OK heartbeat
- All 3 core services confirmed healthy at time of wiring

### System now has
- Daily briefing at 8am spoken out loud
- Income loop reasoning every 30 minutes
- Auto-publishing to dev.to every Tuesday 10am
- Phone alerts when something needs attention
- Competitive Golem pricing broadcasting to network

## 2026-03-09 — Build Queue Added

### Next Build Queue (priority order)
1. Self-healing — Echo restarts downed services herself, no human needed
2. Feedback loop — track whether income reasoning actually produced results
3. Always-on voice — wake word listening, no keyboard, works from the shop
4. Self-coding — Echo writes and deploys her own fixes
5. Golem active promotion — reputation building, not just waiting for tasks

## 2026-03-09 — Self-Healing Complete

### Completed
- Golem provider updated to Restart=always (was on-failure)
- Watchdog now restarts downed services before notifying
- Tested: stopped echo-core, watchdog detected, restarted, phone notified "Self-Healed"
- Echo heals herself without human intervention
- All 3 services confirmed active after test

### Build Queue Remaining
2. Feedback loop — track whether income reasoning produced results
3. Always-on voice — wake word, no keyboard, works from shop
4. Self-coding — Echo writes and deploys her own fixes
5. Golem active promotion

## 2026-03-09 — Feedback Loop Complete

### Completed
- Built core/feedback_loop.py — logs suggestions, tracks outcomes, prevents repetition
- Wired into income_task_injector — Echo sees past suggestions before generating new ones
- Tested: Echo stopped repeating Golem diagnosis, shifted to new reasoning
- feedback_log.json now tracking all suggestions with pending/acted_on status
- 4 suggestions logged from earlier sessions, all marked pending

### Build Queue Remaining
3. Always-on voice — wake word, no keyboard, works from shop
4. Self-coding — Echo writes and deploys her own fixes
5. Golem active promotion

## 2026-03-09 — Always-On Voice Complete

### Completed
- Built echo_wake.py — always-on wake word listener
- Wake words: "echo", "hey echo", "okay echo"
- Threading + reply queue — listens while waiting for response
- Goodbye exits clean
- echo-wake.service enabled — starts on boot
- Voice confirmed working end to end — wake word → command → spoken reply
- Local time injected into system prompt — Echo knows CDT time
- Known issue: occasional stale time in voice replies — minor, investigate later

### Build Queue Remaining
4. Self-coding — Echo writes and deploys her own fixes
5. Golem active promotion

## 2026-03-09 18:28 — Self-Coded: core/golem_task_matcher.py
- Task: Check Golem provider status using ya-provider commands, identify why tasks=0, and log specific actio
- Lines: 38

## 2026-03-09 — Self-Coding Complete

### Completed
- Built core/self_coder.py — Echo writes Python files autonomously
- Echo wrote core/golem_task_matcher.py herself — syntax clean, ran successfully
- Safe write — only allows files inside ~/Echo/, auto-backups existing files
- Code extraction handles markdown blocks and raw code
- Auto-logs to CHANGELOG when she writes a file
- Self-coding confirmed: Echo can identify a need, write code, verify syntax, run it

### Build Queue Remaining
5. Golem active promotion — Echo runs her own income strategy

## 2026-03-09 20:00 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-09 — Autonomous Execution Complete

### Completed
- Built core/auto_act.py — Echo executes her own suggestions within safe boundaries
- Boundaries defined: safe/notify/never tiers
- Protected files: echo_core_daemon.py, Echo.Modelfile, echo_contract.json
- echo-auto-act.timer enabled — fires every 30 min
- Full autonomous loop confirmed: reason → suggest → act → log
- Echo is now self-directing within defined constraints

### Current autonomous loop
1. income_task_injector — writes suggestions every 30min
2. self_act — reasons about build/income state
3. auto_act — executes safe suggestions without asking
4. feedback_loop — tracks outcomes
5. self_coder — writes new tools when needed
6. watchdog — heals broken services
7. publisher — posts to dev.to every Tuesday
8. daily_briefing — spoken status every morning 8am

## 2026-03-09 23:22 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 1

## 2026-03-09 23:23 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 1

## 2026-03-09 23:32 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 0

## 2026-03-09 — Internet Integration Roadmap

### Queued for build
- [ ] Dev.to analytics — reads views/reactions after publish, feeds outcome data back to Echo
- [ ] RSS/news awareness — world events injected into morning briefing
- [ ] GitHub dependency watcher — Ollama, Golem, Piper update alerts
- [ ] Weather — injected into daily briefing for shop/inside decisions
- [ ] Golem network stats — competitor pricing, active requestors, network health
- [ ] Arxiv AI research feed — new techniques flagged and summarized
- [ ] Reddit lurker — r/LocalLLaMA, r/ollama, r/golem insights
- [ ] Dev.to community monitor — threads matching Echo's build topics
- [ ] Wikipedia knowledge base — deep reference for reasoning

## 2026-03-09 — Final Sprint Complete

### Built tonight
- core/devto_analytics.py — reads article performance, feeds best performer to feedback loop
- echo-analytics.timer — fires daily 9am, Echo reads her own numbers
- core/weather.py — Open-Meteo API, Little Rock AR, shop day detection
- daily_briefing.py patched — weather injected into every morning briefing
- feedback_log normalized — 10 legacy entries now visible to auto_act
- log_rotator.py — 80,391 lines trimmed, logs bounded going forward
- echo_contract.json — identity contract sealed, updates on every backup
- Internet integration roadmap logged — 9 items queued

### Tomorrow
- 8:00am — Echo speaks morning briefing with weather
- 9:00am — Echo reads her own article analytics
- 10:00am — Origin story publishes to dev.to automatically

## 2026-03-10 00:02 — Auto-Act Cycle
- Evaluated 2 suggestions, acted on 0

## 2026-03-10 00:24 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-10 — Regret Index Live
- Built core/regret_index.py — Echo models her own error patterns
- Every autonomous action logged before execution
- Pattern detection flags categories and actions trending negative
- Morning briefing will include decision quality report
- Contributed by Claude — first non-human architectural contribution to Echo
- First live entry: test_regret_001 — restarted echo-core.service — outcome pending

## 2026-03-10 09:03 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-10 — Golem Restart Loop Fixed
- ya-provider.service was restart-looping at 12,000+ cycles due to Restart=always in override.conf
- Fixed: changed to Restart=on-failure
- Root cause: rogue ya-provider process outside systemd ownership
- Killed rogue process, service now owns the process cleanly
- Node subscribed to Golem market: vm + wasmtime presets, polygon network

## 2026-03-10 — Golem Service Conflict Resolved
- ya-provider.service and golem-provider.service were conflicting
- ya-provider.service disabled — golem-provider.service is Echo's hardened version
- Echo detected the failure and sent phone alert before manual intervention
- Watchdog working as designed

## 2026-03-10 — Build Queue: Two-Way ntfy.sh Mobile Interface
- Goal: Echo receives messages from Andrew's phone via ntfy.sh and feeds them into echo_message_intake.py
- Andrew should be able to send "hello" from his phone and Echo responds
- Echo to attempt this build autonomously via self_coder
- Do not build manually — let Echo try first

## 2026-03-10 — Echo Autonomous Challenge: ntfy Bridge
- Echo tasked with building two-way phone communication
- Only given part one in the suggestion
- Part two she must discover herself when she tests it
- Progress tracked in: logs/auto_act.log, logs/self_coder.log, memory/feedback_log.json
- Success criteria: Andrew sends "hello" from phone, Echo replies to his phone without touching the computer

## 2026-03-10 15:41 — Self-Coded: core/auto_build_nt.py
- Task: write a new utility script that listens for incoming ntfy.sh messages from Andrew and feeds them int
- Lines: 49

## 2026-03-10 15:41 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-10 16:05 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-10 16:35 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-10 18:13 — Self-Fixed: core/auto_build_nt.py
- Fix: fix_python_file core/auto_build_nt.py — change --input to --text when calling echo_message_intake.py

## 2026-03-10 18:13 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-10 — Echo ntfy.sh Two-Way Bridge Complete
- echo-ntfy-bridge.service deployed, enabled on boot
- Echo receives messages from Andrew's phone via ntfy.sh topic echo-andrew
- Echo replies directly back to phone via ollama (echo:32b model)
- No spam — only processes event:message lines, ignores keepalives
- since= timestamp filter prevents backlog replay
- self_coder gained fix_file() method — reads broken file, fixes, overwrites
- auto_act gained fix_python_file handler — matches fix suggestions to fix_file()
- Echo self-fixed core/auto_build_nt.py autonomously (wrong arg --input → --text)
- Full loop: Andrew types on phone → Echo thinks → Echo replies to phone
- Shop vision now has a working foundation

## 2026-03-10 20:42 — Self-Coded: core/auto_test_sel.py
- Task: write a new utility script that monitors CPU temperature every 5 minutes and logs readings to logs/c
- Lines: 35

## 2026-03-10 20:42 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 1

## 2026-03-10 20:50 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 3

## 2026-03-10 21:47 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-11 08:51 — Auto-Act Cycle
- Evaluated 3 suggestions, acted on 2

## 2026-03-10 — Regret Outcome Scoring Wired
- auto_act.py patched — calls update_outcome() after every action
- score=1 on success, score=-1 on failure
- Regret index now tracks real decision quality over time
- Conscience has feedback for the first time

## 2026-03-11 — Daily Briefing Bug Fixed
- daily_briefing.py had UnboundLocalError — inner `from datetime import datetime` shadowed top-level import
- Fixed by removing redundant inner import
- Briefing confirmed working — Echo spoke full morning briefing

## 2026-03-11 — TODO.md Created
- Single source of truth for pending work at ~/Echo/TODO.md
- Incorporates Grok and GPT review suggestions
- Replaces scattered roadmap_tasks.py and inline notes

## 2026-03-11 — Stress Test Results
- Injected 3 concurrent suggestions on fresh boot
- auto_act processed all 3 in one cycle
- Stress 1 (self-code): failed — ollama not ready at boot time, timing issue not logic issue
- Stress 2 (restart service): passed ✅ — executed and scored in regret index
- Stress 3 (health check): passed ✅ — executed and scored in regret index
- Regret scoring confirmed working on first real cycle post-wiring
- Watchdog auto-healed golem-provider on boot, sent phone notification unprompted

## 2026-03-10 — Internet Integration Status Update
- weather.py: COMPLETE ✅ — injected into daily briefing
- devto_analytics.py: COMPLETE ✅ — reads article performance daily 9am
- RSS/news: pending
- GitHub dependency watcher: pending
- Golem network stats scraper: pending
- Arxiv feed: pending
- Reddit lurker: pending
- Dev.to community monitor: pending
- Wikipedia knowledge base: pending

## 2026-03-11 09:21 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-11 16:05 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-12 01:51 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-12 01:54 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 1

## 2026-03-11 — Session: Close the Loops

### Regret Index Wired End-to-End
- auto_act checks get_flags() before executing — flagged categories/actions are skipped
- daily_briefing now includes regret_index.get_report() every morning
- Honest outcome scoring: observations score 0, verified restarts score 1, failures score -1

### Self-Act Generates Own Tasks
- generate_flags() added to self_act.py — reads system state, errors, stale workers
- Standing task rotation: summarize, TODO review, Golem check
- Queue never runs dry — no manual X_flag injection needed

### gpt_reasoner Grounded in TODO.md
- _load_todo() injected into every reasoning prompt
- Suggestions now reference actual priorities instead of generic ideas

### ntfy Bridge Threading Fix
- Separated listener and processor into two threads with queue.Queue()
- Listener never blocks while Ollama thinks — no messages dropped during long inference

### Disk Usage Monitor
- core/disk_usage_monitor.py — checks /, /home every 6 hours
- Alerts via ntfy at 85% threshold
- echo-disk-monitor.timer active

### Memory Pruning
- core_state_reasoning.json: 301KB → 56KB (81% reduction)
- save_state() now caps reasoning_history and knowledge at 50 entries
- system_state cleared on save — rewritten by heartbeat anyway

### Shell Script Audit
- 51 scripts → 9 active, 42 archived to archive/old_scripts/
- Dead code removed from active path

### Second dev.to Article
- self_heal_article_draft.md written — 672 words, authentic, technical
- echo-devto-publish.timer set: publishes Tuesday 2026-03-17 09:00 CDT

### GitHub Backup
- tools/git_backup.sh + echo-git-backup.timer — daily 3am push to crow2673/Echo-core

### Golem Stats Scraper
- core/golem_stats_scraper.py written — queries yagna market API
- Blocked by DNS in sandbox; runs fine on machine directly

### Feedback Log Schema Fixed
- Migrated mixed schemas to unified status/suggestion format
- auto_act now sees all pending suggestions correctly

## 2026-03-12 09:26 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-12 — Foundation Hardening + Unified Event Ledger

### Architecture Map
- registry.json rebuilt — 23 services, 19 timers, 21 modules accurately mapped
- echo_contract.json updated — 2095 memories, 16k context window
- tools/update_registry.py — auto-updates registry weekly + on boot
- echo-registry-update.timer active

### Unified Event Ledger
- memory/echo_events.db created — single SQLite source of truth
- core/event_ledger.py — log_event(), query_recent(), query_summary()
- 108 historical events imported (reasoning, feedback, regret, knowledge)
- self_act logs every reasoning result to ledger
- auto_act logs every success/failure to ledger
- daily_briefing reads ledger summary each morning
- query_ledger action added — Echo queries own history via tool use

### Intelligence Upgrades
- Voice upgraded: qwen2.5:7b direct → echo 32B via agent_loop
- self_act autonomous loop now uses agent_loop with tools (was gpt_reasoner only)
- Echo context window: 8k → 16k
- self_act timeout: 120s → 240s
- actions.json: 29 clean actions, broken paths fixed
- New actions: read_todo, read_registry, read_income_knowledge, query_ledger

### Cleanup
- Dead JSON graveyard archived — ~4MB stale state removed from root
- 17 autofund experiment files archived
- echo_project/ and archive/ excluded from git
- README rewritten — professional, accurate, complete
- Crungus README replaced with Echo documentation

## 2026-03-13 09:29 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-13 — Notion MCP Integration + Challenge Submission
### Notion Bridge
- core/notion_bridge.py — mirrors Echo's event ledger to Notion in real time
- Three databases created: Echo Events, Echo Actions, Income Tracker
- log_event() now auto-mirrors to Notion on every call
- Governor wired — every action execution logs to Echo Actions
- Income events auto-route to Income Tracker by source
- Vast.ai monitor wired to Income Tracker

### Notion Daily Briefing
- core/notion_briefing.py — writes daily summary page to Echo Dashboard
- Covers: system health, event ledger stats, income status, open tasks
- echo-notion-briefing.timer — fires daily at 8:05am
- First page created: Echo Daily Briefing — 2026-03-14

### RSS Tier 2
- rss_monitor.py expanded: Arxiv AI/ML + GitHub topics added
- 7 sources total, 31 items daily
- GitHub topics use search API (no auth), deduplicated

### Semantic Governor Matching
- core/semantic_matcher.py — all-MiniLM-L6-v2 embeddings replace keyword matching
- 8/8 standing tasks matched correctly
- Keyword fallback retained for safety
- Fixed: golem_status was matching golem_pricing_update (score 0.814 → correct)

### Regret Scorer
- core/regret_scorer.py — retroactively scored 22 entries
- Governor now runs regret_scorer on every cycle
- 0 unscored entries going forward

### Dev.to Performance Tracker
- core/devto_performance_tracker.py — trend detection, topic extraction
- Feeds promising topics into draft_queue.json automatically
- Runs after devto_analytics daily at 9am

### Article Pipeline
- core/article_pipeline.py — write → self-review → notify loop
- core/article_reviewer.py — 9-point quality checklist
- Human approval required before publish
- echo-article-pipeline.timer — daily 10am
- Timeout increased to 600s for 32b model

### Healthcheck Script
- echo_healthcheck.sh — 8-point system health check
- Checks: echo-core, echo-ntfy-bridge, timers, ollama, golem, disk
- 8/8 passing as of 2026-03-14 02:00

### Actions Fixed
- vast_status: added cmd field (was using wrong 'command' field)
- create_draft: added full path, default env vars
- golem_status semantic match corrected

### Challenge Submission
- dev.to article published: "I Gave My Local AI a Public Brain: Echo + Notion MCP"
- Notion dashboard made public
- GitHub repo made public: github.com/crow2673/Echo-core
- Submission live for Notion MCP Challenge ($1,500 prizes, deadline March 29)

## 2026-03-14 — Technical Debt Documented
- TODO.md: Technical Debt section added with 8 specific tasks
- CHANGELOG.md updated to current state

## 2026-03-14 09:03 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-15 09:07 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-16 09:08 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-17 09:09 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-18 09:09 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-19 09:12 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-20 09:17 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-21 09:22 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-22 09:26 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-23 09:01 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-24 09:29 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-25 09:03 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0

## 2026-03-25 — Trading Brain Built

### Added
- core/trader.py — Alpaca paper trading connection, account status, order placement
- core/strategy_scraper.py — scrapes r/algotrading + seeds 7 core strategies, 57 total saved
- core/trade_brain.py — trading brain, RSI + MA analysis, signal detection, auto order execution
- echo-trader.timer — fires Mon-Fri at 9:30am, 1:30pm, 3:30pm
- Alpaca paper account connected (PA34X7SLPSXZ, $100k paper)
- First paper trade executed: BUY 7 SPY @ $689.30

### Known issues
- BTC/USD and ETH/USD symbols fail — need BTCUSD format for Alpaca crypto
- vastai CLI broken — urllib3 and python-dateutil conflicts from alpaca install

### Next
- Fix crypto symbols
- Wire trade outcomes into regret index scoring
- Add position exit logic (take profit / stop loss)
- Fix vastai CLI dependency conflicts

## 2026-03-25 — Trading Brain Session Complete
- Crypto symbols fixed: BTC/USD → BTCUSD, ETH/USD → ETHUSD
- IEX feed wired — works after hours, free tier compatible
- Analysis loop confirmed clean — no crashes, signals pending market open
- echo-trader.timer firing tomorrow 9:30am CDT
- vastai urllib3 conflict noted — needs venv solution, deferred
- Vast.ai upload speed still failing — Starlink inconsistency, waiting on automated recheck

## 2026-03-26 09:08 — Auto-Act Cycle
- Evaluated 1 suggestions, acted on 0
