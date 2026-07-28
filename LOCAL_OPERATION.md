# Echo Local Operation Guide

This guide is for temporary maintenance-mode operation when Echo should run
without ChatGPT, Claude, Codex, or model training.

## Maintenance-Mode Baseline

Echo should keep these local components active:

- `echo-core.service`
- `echo-telegram-intake.timer`
- `echo-heartbeat.timer`
- `echo-pulse.timer`
- `echo-homeostasis.timer`
- Ollama with `qwen2.5:7b`

Echo should keep these disabled unless Andrew explicitly restores them:

- `echo-conductor-agents.service`
- `echo-conductor-agents-repair.timer`
- `echo-finetune.timer`

The explicit local-only flag is:

```bash
cat ~/Echo/memory/local_operation_mode.json
```

When this file has `"enabled": true`, Homeostasis should not treat the
intentionally disabled Claude/Codex conductor repair timer as a core failure.

## Startup Commands

Start local-only Echo services:

```bash
cd ~/Echo
systemctl --user start echo-core.service
systemctl --user start echo-telegram-intake.timer
systemctl --user start echo-heartbeat.timer
systemctl --user start echo-pulse.timer
systemctl --user start echo-homeostasis.timer
ollama ps
```

Make local-only mode persistent across reboot:

```bash
systemctl --user enable echo-core.service
systemctl --user enable echo-telegram-intake.timer
systemctl --user enable echo-heartbeat.timer
systemctl --user enable echo-pulse.timer
systemctl --user enable echo-homeostasis.timer
systemctl --user disable echo-conductor-agents.service
systemctl --user disable echo-conductor-agents-repair.timer
systemctl --user disable echo-finetune.timer
printf '%s\n' '{"enabled": true, "reason": "Temporary local-only operation without Claude/Codex or autonomous fine-tuning."}' > ~/Echo/memory/local_operation_mode.json
```

## Shutdown Commands

Stop Echo's local runtime:

```bash
systemctl --user stop echo-telegram-intake.timer
systemctl --user stop echo-heartbeat.timer
systemctl --user stop echo-pulse.timer
systemctl --user stop echo-homeostasis.timer
systemctl --user stop echo-core.service
```

Stop optional collaboration/fine-tune paths:

```bash
systemctl --user disable --now echo-conductor-agents.service
systemctl --user disable --now echo-conductor-agents-repair.timer
systemctl --user disable --now echo-finetune.timer
```

## Health-Check Commands

Core service and timers:

```bash
systemctl --user --no-pager --failed
systemctl --user --no-pager status echo-core.service
systemctl --user --no-pager status echo-telegram-intake.timer echo-telegram-intake.service
systemctl --user --no-pager status echo-heartbeat.timer echo-pulse.timer echo-homeostasis.timer
```

Homeostasis and Executive Context:

```bash
cd ~/Echo
python3 tools/homeostasis_check.py --print
python3 -m core.executive_context --print
```

Pulse and heartbeat:

```bash
cd ~/Echo
tail -20 logs/pulse.log
tail -20 memory/experience_log.jsonl
```

Local model:

```bash
ollama ps
ollama run qwen2.5:7b "Local health check. Reply with exactly: ECHO_LOCAL_OK"
```

Collaboration relay disabled-state check:

```bash
cd ~/Echo
python3 -c 'from core.conductor import load_agents,pane_state; import json; print(json.dumps({h:pane_state(t) for h,t in load_agents().items()}, indent=2))'
```

Expected maintenance-mode result: Claude and Codex are `missing` or
`unavailable`, not `ready`.

## Telegram Troubleshooting

Telegram requires internet and a valid bot token. If local model replies work
but Telegram does not:

```bash
systemctl --user --no-pager status echo-telegram-intake.timer echo-telegram-intake.service
journalctl --user -u echo-telegram-intake.service --no-pager -n 120
tail -120 ~/Echo/logs/telegram_intake.log
```

Check local configuration without printing secrets:

```bash
cd ~/Echo
python3 tools/validate_secrets.py
```

If Telegram is temporarily unavailable, Echo can still run local health checks,
memory operations, and CLI tests from the terminal.

## Model Troubleshooting

Confirm Ollama is reachable:

```bash
ollama ps
ollama list
ollama run qwen2.5:7b "Reply with OK"
```

If the GPU is busy or memory is tight:

```bash
nvidia-smi
ollama stop llama3.1:latest
ollama stop qwen2.5vl:7b
ollama run qwen2.5:7b "Reply with OK"
```

Do not pull or install new models during maintenance mode unless Andrew
explicitly approves it.

## Backup And Restore

Git protects source code only. Runtime memory, SQLite databases, logs, private
media, interaction ledgers, and local state are intentionally not committed.

Check recent local/offsite backup marker:

```bash
cd ~/Echo
cat memory/offsite_backup_last.txt
ls -lah memory/offsite_backups 2>/dev/null
```

Create a local encrypted/offsite backup only when Andrew approves:

```bash
cd ~/Echo
python3 tools/offsite_backup.py --dry-run
python3 tools/offsite_backup.py
```

Emergency local source checkpoint:

```bash
cd ~/Echo
git status --short
git log -5 --oneline
```

Restore source code to the latest committed version only after Andrew approves:

```bash
cd ~/Echo
git status --short
git show --stat --oneline HEAD
```

Do not run destructive Git commands during maintenance mode unless Andrew gives
explicit approval.

## Known Blockers

- Claude and Codex tmux workers are intentionally disabled for local-only mode.
- Fine-tuning is disabled and must be started manually by Andrew.
- Telegram requires internet and Telegram API access.
- Dev.to publishing, Gmail, Fiverr, Vast, trading APIs, offsite delivery, and
  other external capabilities require internet and credentials.
- Current income-related blockers may remain visible as capability blockers.

## Actions Echo Must Not Perform Autonomously

Echo must not autonomously:

- train or fine-tune models
- spend money
- place trades or move financial assets
- publish public content
- send outreach, email, or third-party messages
- make purchases or order parts
- operate vehicles, robotics, machinery, furnace equipment, tools, or hazardous systems
- approve Claude, Codex, browser, shell, or permission prompts
- convert pending observations, visual labels, workspace changes, or conversation
  candidates into permanent facts, tasks, or training data without Andrew review
- delete, rewrite, or migrate private runtime memory without explicit approval

## Emergency Recovery Commands

Return to local-only maintenance mode:

```bash
cd ~/Echo
systemctl --user disable --now echo-conductor-agents.service
systemctl --user disable --now echo-conductor-agents-repair.timer
systemctl --user disable --now echo-finetune.timer
printf '%s\n' '{"enabled": true, "reason": "Temporary local-only operation without Claude/Codex or autonomous fine-tuning."}' > ~/Echo/memory/local_operation_mode.json
systemctl --user restart echo-core.service
systemctl --user restart echo-telegram-intake.timer
systemctl --user restart echo-heartbeat.timer
systemctl --user restart echo-pulse.timer
systemctl --user restart echo-homeostasis.timer
systemctl --user --no-pager --failed
python3 tools/homeostasis_check.py --print
ollama run qwen2.5:7b "Reply with exactly: ECHO_LOCAL_OK"
```

If Telegram is broken but local Echo is healthy, use the terminal until
internet or Telegram credentials are restored.
