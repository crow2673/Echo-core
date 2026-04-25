#!/bin/bash
cd ~/Echo

# Stage meaningful files only — no runtime state, no junk, no .bak files
git add \
  core/ tools/ builds/ \
  echo_core_daemon.py Echo.Modelfile registry.json \
  TODO.md CHANGELOG.md README.md ARCHITECTURE.md CLAUDE.md \
  memory/content_strategy.json memory/known_gaps.md \
  memory/income_knowledge.md memory/world_context.md \
  memory/standing_tasks.json memory/session_summary.json \
  .gitignore \
  2>/dev/null

# Skip if nothing changed
git diff --cached --quiet && exit 0

# Count changed files for a useful message
CHANGED=$(git diff --cached --name-only | wc -l)
git commit -m "Auto backup $(date +%Y-%m-%d\ %H:%M) — ${CHANGED} files"
git push origin main
