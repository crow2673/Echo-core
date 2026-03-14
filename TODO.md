# Echo TODO — Last updated 2026-03-14

## In Progress / Waiting
- [ ] Golem new node penalty — wait 7-14 days, then benchmark pricing with: python3 -m core.golem_stats_scraper

- [ ] Video demo for Notion challenge — 2-3 min screen recording, upload YouTube unlisted, embed in article (deadline March 29)

## Income
- [ ] Income closure — Golem earning path clear, dev.to publishing, no dollar yet
- [ ] Autonomous article pipeline — Echo writes, self-reviews, adjusts, then queues for human approval before publish
- [x] Memory promotion layer — retrieval count + outcome score + recency decay DONE 2026-03-14 to rank what's worth keeping (from Daniel Nwaneri exchange)
- [ ] Echo Shell / setup wizard — END GOAL, prove income first

## Hardware
- [ ] Shop voice: better VAD/noise-cancel + directional mic
- [ ] Jetson Orin AGX integration

## Long Horizon
- [ ] Speculative execution / tool-use caching to reduce 32b latency
- [ ] Stage 7: hybrid routing — hard questions to cloud API, easy to local echo

## Architecture
- [x] Unified state/event model — SQLite event ledger (memory/echo_events.db)
- [x] Stage 6: orchestrated agency — governor.py live, reason→act→score loop closed
- [x] Semantic governor matching — all-MiniLM-L6-v2, 8/8 standing tasks DONE 2026-03-13
- [x] RSS tier 1 — dev.to, HN, r/LocalLLaMA, Golem, Ollama DONE 2026-03-13
- [x] RSS tier 2 — Arxiv AI/ML + GitHub topics, 7 sources 31 items daily DONE 2026-03-13
- [x] Regret scorer — 22 backfilled, governor auto-scores DONE 2026-03-13
- [x] Dev.to performance tracker — trend detection, draft queue injection DONE 2026-03-13
- [x] Vast.ai dedicated action — vast_status action #38 DONE 2026-03-13
- [x] Article pipeline — write→review→notify loop, human approval before publish DONE 2026-03-13
- [x] Notion MCP integration — 3 databases, live mirroring, daily briefing DONE 2026-03-14
- [x] Healthcheck script — 8/8 checks, works from any context DONE 2026-03-14

## Technical Debt — ALL RESOLVED 2026-03-14
- [x] Clean root directory — archived 116MB logs + 66 bak files + Gai legacy
- [x] Notion bridge timeout — retry logic with backoff
- [x] Notion bridge async — background thread, never blocks Echo
- [x] Article pipeline timeout — ollama idle check
- [x] actions.json schema — all 38 actions use cmd field consistently
- [x] Governor keyword fallback — kept as safety net, fixed dead vast_status branch
- [x] Memory file cleanup — trading bot ndjson archived
- [x] 4.9GB VRAM freed — Gai model unloaded, not called by active code

## Completed (Earlier Sessions)
- [x] Vast.ai host registered — machine 57470, RTX 3060, $0.10/hr
- [x] ARCHITECTURE.md — technical reference complete
- [x] Hardening audit — 2 redundant timers removed
- [x] Golem pricing control — core/golem_pricing.py, safe bounds
- [x] Draft writer — core/draft_writer.py
- [x] Ethernet up — enp7s0 192.168.1.145
- [x] Regret loop closed — flags block bad patterns
- [x] ntfy bridge threading — never blocks
- [x] Disk usage monitor — every 6h, alerts at 85%
- [x] Self-heal article — publishes Tuesday 2026-03-17 09:00 CDT
- [x] GitHub backup — daily 3am push to crow2673/Echo-core
- [x] Crown a king — echo_core_daemon.py as single orchestrator
- [x] ntfy two-way phone bridge — echo-ntfy-bridge.service
- [x] Watchdog auto-heal on boot
- [x] Weather integration
- [x] Dev.to analytics
