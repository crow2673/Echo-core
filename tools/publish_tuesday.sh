#!/bin/bash
# tools/publish_tuesday.sh — publishes next queued dev.to article
# Runs Tuesday 9am via echo-devto-publish.timer

set -euo pipefail

BASE="$HOME/Echo"
LOG="$BASE/logs/devto_publish.log"

mkdir -p "$(dirname "$LOG")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

log "=== Tuesday publish starting ==="

cd "$BASE"

# Check if there's a draft ready to publish
python3 - <<'PYEOF'
import json
import sys
from pathlib import Path

BASE = Path.home() / "Echo"
strategy_file = BASE / "memory/content_strategy.json"

if not strategy_file.exists():
    print("No content_strategy.json found")
    sys.exit(0)

strategy = json.loads(strategy_file.read_text())
queue = strategy.get("queue", [])
drafts = [a for a in queue if a.get("status") == "draft"]

if not drafts:
    print("No drafts ready to publish")
    sys.exit(0)

next_draft = drafts[0]
draft_file = next_draft.get("draft_file", "")
title = next_draft.get("title", "")

if not draft_file or not Path(draft_file).exists():
    print(f"Draft file missing: {draft_file}")
    sys.exit(0)

print(f"Publishing: {title[:60]}")
sys.exit(10)  # signal that a draft is ready
PYEOF

STATUS=$?

if [ "$STATUS" -eq 10 ]; then
    log "Draft found — publishing via echo_devto_publisher.py"
    python3 "$BASE/echo_devto_publisher.py" --from-session 2>&1 | tee -a "$LOG" || true
else
    log "No draft to publish — generating new article"
    python3 "$BASE/echo_devto_publisher.py" --from-session 2>&1 | tee -a "$LOG" || true
fi

log "=== Tuesday publish complete ==="
