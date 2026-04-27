#!/bin/bash
# tools/finetune_pipeline.sh — Echo soul fine-tuning pipeline
# Runs monthly on the 1st at 2am via echo-finetune.timer
# Fine-tunes a local model on Echo's conversation history

set -euo pipefail

BASE="$HOME/Echo"
LOG="$BASE/logs/finetune.log"
DATA_DIR="$BASE/memory/finetune_data"
TIMESTAMP=$(date +"%Y%m%d_%H%M")

mkdir -p "$DATA_DIR"
mkdir -p "$(dirname "$LOG")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

log "=== Fine-tune pipeline starting: $TIMESTAMP ==="

# Export recent exchanges as training data
log "Exporting conversation data..."
python3 - <<'PYEOF'
import json
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path.home() / "Echo"
mem_file = BASE / "echo_memory.json"
data_dir = BASE / "memory/finetune_data"
data_dir.mkdir(parents=True, exist_ok=True)

if not mem_file.exists():
    print("No memory file found")
    exit(0)

try:
    mem = json.loads(mem_file.read_text())
    exchanges = mem.get("exchanges", [])
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    recent = [e for e in exchanges if e.get("ts", "") >= cutoff]

    if len(recent) < 10:
        print(f"Only {len(recent)} exchanges — skipping fine-tune")
        exit(0)

    # Format as JSONL for Ollama
    out = []
    for e in recent:
        user = e.get("user", "").strip()
        echo = e.get("echo", "").strip()
        if user and echo and len(echo) > 20:
            out.append({"prompt": user, "response": echo})

    out_file = data_dir / f"exchanges_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(out_file, "w") as f:
        for item in out:
            f.write(json.dumps(item) + "\n")
    print(f"Exported {len(out)} training examples to {out_file.name}")
except Exception as e:
    print(f"Export error: {e}")
    exit(1)
PYEOF

log "Fine-tune data exported"
log "Note: Ollama fine-tuning via modelfile — manual trigger required for GPU run"
log "=== Fine-tune pipeline complete ==="
