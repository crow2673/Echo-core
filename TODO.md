# Echo TODO — Last updated 2026-03-12

## In Progress / Waiting
- [ ] Golem new node penalty — wait 7-14 days, then benchmark pricing with: python3 -m core.golem_stats_scraper
- [ ] Regret index — needs volume, run for a week before patterns emerge
- [ ] Internet roadmap tier 1 — RSS feed + dev.to monitor, scope next session

## Architecture
- [x] Unified state/event model — SQLite event ledger (memory/echo_events.db)
- [ ] auto_act action surface — only 5 action types, needs more verifiable actions
- [ ] Stage 6: orchestrated agency — full governor with event ledger as source of truth

## Immediate (Next Session)
- [ ] Vast.ai / RunPod account — register RTX 3060, first passive income
- [ ] ARCHITECTURE.md — deeper technical doc for contributors

## Income
- [ ] Income closure — Golem earning path clear, dev.to publishing, no dollar yet
- [ ] Echo Shell / setup wizard — END GOAL, prove income first

## Hardware
- [ ] Shop voice: better VAD/noise-cancel + directional mic
- [ ] Jetson Orin AGX integration

## Long Horizon
- [ ] Speculative execution / tool-use caching to reduce 32b latency
- [ ] Internet roadmap tier 2 — Arxiv, Reddit lurker, GitHub watcher

## Completed
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
