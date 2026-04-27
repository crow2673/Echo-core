# Known Gaps — What Echo Is Missing
# Echo reads this during self_review_tasks to guide build proposals.
# Andrew updates this. Echo proposes builds to close them.

## GOLEM — CLOSED INVESTIGATION (do not re-open without new information)
**Diagnosis confirmed 2026-04-23 by Andrew + Claude Code. Stop proposing Golem logging/monitoring builds.**

The Golem provider (ya-provider PID 3793445) is running correctly. It has:
- 2 active offers on the market (vm + wasmtime runtimes)
- A real public Starlink IP (153.66.239.119) — NOT behind CGNAT. The CGNAT theory was wrong.
- Docker available for vm runtime
- Competitive pricing (0.0001 GLM/CPU-sec)
- 0 agreements in its entire history

**Root cause of zero tasks: market demand, not connectivity.**
The Golem network has thousands of CPU providers and very few requestors. CPU-only nodes routinely sit idle for months. The RTX 3060 is not configured for GPU tasks — GPU providers get the majority of actual work. Improving Golem logging will not fix this. Monitoring Golem connection stability will not fix this. There is nothing broken to fix.

**What would actually help:** Configure the RTX 3060 as a GPU provider (requires nvidia-container-toolkit + ya-provider GPU plugin). This is a real build task if Andrew decides Golem is worth pursuing. Until then, treat Golem income as $0 and do not allocate reasoning cycles to it.

## GIT SAFETY — LEARNED 2026-04-26 (do not forget)

**`git filter-repo` wipes files from disk when it drops commits.**

On 2026-04-26, Andrew and Claude Code squashed 49 "Auto backup" commits using `git filter-repo`. This rewrote the working tree to match the new HEAD. Every file that existed ONLY in those auto backup commits was deleted from disk — 15 core modules and memory files were lost and had to be rebuilt from scratch.

**Rule: never propose or run a git history rewrite (filter-repo, rebase -i, reset --hard) without first confirming every important file has a named non-backup commit.**

The correct order is: commit meaningful work under a descriptive name → THEN clean history. Never backwards.

If you are ever tempted to propose "squash the auto backup commits" — read this first.

## High Priority Gaps
- Need a script to monitor and log system performance metrics and alert if they fall outside expected ranges.  _(identified by Echo 2026-04-27 03:46)_
- Need a script to monitor and manage system alerts and notifications more efficiently, ensuring no important alerts are missed.  _(identified by Echo 2026-04-26 21:46)_

- No outreach script — demand_scanner finds leads (score ≥ 7) but Echo cannot contact them (Reddit OAuth write scope required for DMs/comments)
- No script tracks Fiverr gig view count over time (manual check required now)
- No script monitors Echo logs for ERROR patterns and sends a daily digest
- No script watches for new Reddit posts mentioning the Fiverr gig name

## Recently Closed (2026-04-24)
- ✅ Daily activity summary — tools/daily_summary.py fires at 8pm via echo-daily-summary.timer
- ✅ Ollama watchdog — tools/ollama_watchdog.py fires every 10min via echo-ollama-watchdog.timer
- ✅ Offsite backup — tools/offsite_backup.py encrypts soul docs and emails to Gmail at 3:30am
- ✅ Disk usage monitor — core/disk_usage_monitor.py (already running via echo-disk-monitor.timer)

## Medium Priority Gaps

- No script monitors RAM usage and warns when qwen2.5:32b is about to OOM
- No script auto-restarts stale systemd timers that haven't fired in 2x their interval
- No script validates that all secrets in golem.env are still valid (test API calls)
- No content repurposing — dev.to articles not posted to Beehiiv newsletter automatically
- session_checkpoint is being blocked by dispatcher cooldown — nightly memory write skipped

## Low Priority Gaps

- No script tracks weather (Andrew mentioned chronic pain — barometric pressure alerts)
- No weekly Fiverr competitor analysis (what are others charging?)
