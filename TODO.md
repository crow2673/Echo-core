# Echo TODO — Last updated 2026-03-13

## In Progress / Waiting
- [ ] Golem new node penalty — wait 7-14 days, then benchmark pricing with: python3 -m core.golem_stats_scraper
- [x] Regret index — retroactively scored, governor auto-scores new entries DONE 2026-03-13
- [x] Internet roadmap tier 1 — RSS feed + dev.to monitor DONE 2026-03-13

## Architecture
- [x] Unified state/event model — SQLite event ledger (memory/echo_events.db)
- [x] auto_act action surface — 29→36 actions: notify_phone, append_todo, golem_pricing, devto_publish, create_draft, golem_diagnostic
- [x] Stage 6: orchestrated agency — governor.py live, reason→act→score loop closed

## Immediate (Next Session)
- [x] Vast.ai host registered — machine 57470, RTX 3060, $0.10/hr, Arkansas US, live
- [x] ARCHITECTURE.md — 234 lines, technical reference complete

## Income
- [ ] Income closure — Golem earning path clear, dev.to publishing, no dollar yet
- [ ] Autonomous article pipeline — Echo writes, self-reviews, adjusts, then queues for human approval before publish
- [ ] Echo Shell / setup wizard — END GOAL, prove income first

## Hardware
- [ ] Shop voice: better VAD/noise-cancel + directional mic
- [ ] Jetson Orin AGX integration

## Long Horizon
- [ ] Speculative execution / tool-use caching to reduce 32b latency
- [x] Internet roadmap tier 2 — Arxiv + GitHub watcher DONE 2026-03-13

## Completed
- [x] Semantic governor matching — all-MiniLM-L6-v2, 8/8 standing tasks, keyword fallback DONE 2026-03-13
- [x] Regret scorer — 22 backfilled, auto-scores on every governor cycle DONE 2026-03-13
- [x] Dev.to performance tracker — trend detection, topic extraction, draft queue injection DONE 2026-03-13
- [x] Vast.ai dedicated action — vast_status action #37, semantic matcher updated DONE 2026-03-13
- [x] RSS tier 2 — Arxiv AI/ML + GitHub topics, 7 sources 31 items daily DONE 2026-03-13

- [x] Hardening audit — 2 redundant timers removed (echo-backup, echo-income-injector)
- [x] Golem pricing control — core/golem_pricing.py, all presets dropped to attract tasks
- [x] Draft writer — core/draft_writer.py, Echo can write and queue dev.to articles autonomously
- [x] Ethernet up — enp7s0 192.168.1.145, WiFi stays primary for Vast.ai public IP
- [x] Vast.ai API key fixed — crow2673 account, machine_read permission, vast_monitor working
- [x] Regret loop closed — flags block bad patterns, briefing reports it
- [x] TODO wired into gpt_reasoner — suggestions grounded in real priorities
- [x] ntfy bridge threading — listener + processor threads, never blocks
- [x] Disk usage monitor — every 6h, alerts at 85%
- [x] Golem stats scraper — written, ready at core/golem_stats_scraper.py
- [x] Shell script audit — 42 archived, 9 active remain
- [x] Self-heal article — publishes Tuesday 2026-03-17 09:00 CDT
- [x] GitHub backup — daily 3am push to crow2673/Echo-core
- [x] Memory pruning — 301KB → 56KB, capped at 50 entries
- [x] Self-act generates own X_flags — queue never runs dry
- [x] Honest outcome scoring — observations score 0, verified actions score 1
- [x] Feedback log schema unified
- [x] Old shell scripts audit — 42 archived
- [x] Crown a king — echo_core_daemon.py as single orchestrator
- [x] auto_act double-firing bug — lockfile added
- [x] Offsite backup — git push to crow2673/Echo-core, daily 3am timer
- [x] Second dev.to article — self-heal story, publishes Tuesday 2026-03-17 9am CDT
- [x] Wire regret_index into auto_act — score=1 success, score=-1 failure
- [x] self_coder fix_file() method
- [x] ntfy two-way phone bridge — echo-ntfy-bridge.service
- [x] Watchdog auto-heal on boot
- [x] Weather integration
- [x] Dev.to analytics

## Technical Debt (Harden & Clean)
- [x] Clean root directory — archived 116MB logs + 66 bak files DONE 2026-03-14 in ~/Echo/ root need archiving (daemon.log 2MB, jarvis.log 100MB, echo_agi_lite.log 2MB, autonomous.log 500KB)
- [x] Notion bridge timeout — retry logic with backoff added DONE 2026-03-14 hitting Notion API, needs retry logic with backoff in core/notion_bridge.py
- [x] Article pipeline timeout — ollama idle check added, skips if busy DONE 2026-03-14 because governor is competing for Ollama, needs queue-aware scheduling
- [x] actions.json schema — all 38 actions use cmd field consistently DONE 2026-03-14 caused silent failures, audit all 38 actions for consistency
- [x] Root directory .bak files — all 66 archived DONE 2026-03-14 in root, need archiving to checkpoints/
- [x] Governor keyword fallback — kept as safety net, fixed dead vast_status branch DONE 2026-03-14
- [x] Memory file cleanup — trading bot ndjson archived DONE 2026-03-14 (4.3MB) and echo_memory.legacy.ndjson (9.6MB) in root, should move to archive
- [x] Notion bridge async — background thread, never blocks Echo DONE 2026-03-14 on each API call, should run in background thread to never slow Echo down
