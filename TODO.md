# Echo TODO — Last updated 2026-03-31

## HIGH PRIORITY
- [ ] Crown a king Phase 2B — patch ready from Grok, apply next session. Add load_echo_state() + replace health loop
- [ ] Crown a king Phase 3 — timers become dumb workers, daemon makes all decisions
- [ ] Yagna publicAddress null — Starlink CGNAT, needs VPN or Starlink Priority
- [ ] auto_act double-firing — flock partial fix, root cause still unknown
- [ ] Offsite backup — encrypted git push of echo_contract.json + soul document
- [ ] Fix vastai CLI — urllib3/alpaca conflict, needs venv

## MEDIUM PRIORITY
- [ ] Briefing session context — "Last build focus not confirmed", needs real source in Phase 3
- [ ] Fix ETHUSD symbol for Alpaca
- [ ] ntfy bridge threading — reply queue
- [ ] Internet roadmap: RSS, GitHub watcher, Arxiv, Reddit lurker
- [ ] Old shell scripts audit — 40+ from Dec/Jan
- [ ] Paper trading — monitor 30 days before live money

## LOW PRIORITY / FUTURE
- [ ] Shop voice — VAD/noise-cancel + directional mic
- [ ] Speculative execution / tool-use caching
- [ ] Echo Shell / setup wizard — END GOAL
- [ ] Jetson Orin AGX integration
- [ ] Stage 6: orchestrated agency — full governor with event ledger

## COMPLETED
- [x] Crown a king Phase 1 — governor_v2.py + echo_state.json live every 5 min
- [x] Crown a king Phase 2A — briefing reads from echo_state.json, live stats
- [x] Trading brain fully autonomous — opens/manages/closes positions
- [x] Two strategies: trend (large caps) + momentum (quick movers)
- [x] Trade outcomes wired into regret index
- [x] Exit logic — trend 4%/2.5%, momentum 2%/1%
- [x] Content strategy — 8 weeks of real topics wired into draft_writer
- [x] Article pipeline flood fixed — governor dedup check
- [x] Publisher fixed — --from-session
- [x] Notion dashboard reorganized — command center rebuilt
- [x] Analytics handler in auto_act — no more false regret failures
- [x] Golem showing Online — yagna restarted on Starlink
- [x] Alpaca paper trading — $100k paper, 3 positions open
- [x] Strategy scraper — 57 strategies seeded
