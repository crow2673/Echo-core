# Echo TODO

## In Progress / Waiting
- [ ] Golem new node penalty — wait 7-14 days, then benchmark pricing with: python3 -m core.golem_stats_scraper
- [ ] Regret index — needs volume, run for a week before patterns emerge
- [ ] Internet roadmap tier 1 — RSS feed + dev.to monitor, scope next session

## Architecture
- [ ] Unified state/event model — SQLite event ledger, one source of truth
- [ ] auto_act action surface — only 5 action types, needs more verifiable actions
- [ ] Stage 6: orchestrated agency — full governor with event ledger as source of truth

## Income
- [ ] Income closure — Golem earning path clear, dev.to publishing, no dollar yet
- [ ] Echo Shell / setup wizard — END GOAL, prove income first

## Hardware
- [ ] Shop voice: better VAD/noise-cancel + directional mic
- [ ] Jetson Orin AGX integration

## Long Horizon
- [ ] Speculative execution / tool-use caching to reduce 32b latency
- [ ] Internet roadmap tier 2 — Arxiv, Reddit lurker, GitHub watcher

## Completed This Session (2026-03-11)
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
