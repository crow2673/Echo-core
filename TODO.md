# Echo TODO — Last updated 2026-03-11

## IN QUEUE (auto_act will attempt)
- [x] Two-way ntfy bridge — listener + processor threads, queue-based, never blocks
- [x] Disk usage monitor — runs every 6h, alerts at 85%

## HIGH PRIORITY
- [x] Crown a king — consolidate all timers/workers under echo_core_daemon.py as single orchestrator
- [ ] Unified state/event model — one source of truth instead of split across logs/JSON/DB
- [ ] Golem stats scraper — written, blocked by DNS in sandbox; test manually with: python3 -m core.golem_stats_scraper
- [ ] Golem stats scraper — needs api.stats.golem.network access, script ready at core/golem_stats_scraper.py
- [x] auto_act double-firing bug — lockfile added
- [x] Offsite backup — encrypted git push to crow2673/Echo-core, daily 3am timer

## MEDIUM PRIORITY
- [ ] Internet roadmap: RSS feed, GitHub watcher, Arxiv, Reddit lurker, dev.to community monitor
- [ ] Second dev.to article — self-heal story (next Tuesday auto-publish)
- [ ] Old shell scripts audit — 40+ scripts from Dec/Jan, half likely dead
- [x] Echo briefing RAM/swap accuracy — psutil fix applied

## LOW PRIORITY / FUTURE
- [ ] Shop voice: better VAD/noise-cancel + directional mic for noisy environment
- [ ] Speculative execution or tool-use caching to reduce 32b latency
- [ ] Echo Shell / setup wizard — END GOAL, prove income first
- [ ] Jetson Orin AGX integration
- [ ] Stage 6: orchestrated agency — full governor with event ledger as source of truth

## COMPLETED
- [x] Wire regret_index outcome scoring into auto_act (score=1 success, score=-1 failure)
- [x] Regret index update_outcome() wired — pattern detection now has real data
- [x] self_coder gained fix_file() method
- [x] auto_act gained fix_python_file handler
- [x] Echo self-fixed core/auto_build_nt.py autonomously
- [x] ntfy two-way phone bridge deployed as systemd service (echo-ntfy-bridge.service)
- [x] CPU temp monitor written by Echo from scratch
- [x] Briefing transcript log added
- [x] daily_briefing.py datetime bug fixed
- [x] Stress test passed — 2/3 suggestions executed, regret scoring confirmed working
- [x] Watchdog auto-healed on boot unprompted
- [x] Weather integration complete
- [x] Dev.to analytics complete
