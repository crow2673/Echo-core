#!/bin/bash
# tools/finetune_pipeline.sh — Echo soul fine-tuning pipeline
# Runs weekly (Sunday 2am) via echo-finetune.timer
# Full chain: check reviewed examples → train LoRA → merge → GGUF → Ollama

set -euo pipefail

BASE="$HOME/Echo"
LOG="$BASE/logs/finetune.log"
DATASET="$BASE/memory/finetune_dataset_reviewed.jsonl"
VENV="$BASE/venv"
TIMESTAMP=$(date +"%Y%m%d_%H%M")

mkdir -p "$(dirname "$LOG")"
cd "$BASE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

log "=== Fine-tune pipeline starting: $TIMESTAMP ==="

log "--- Preflight: Exporting reviewed conversation-learning candidates ---"
python3 -m core.conversation_learning_candidates --export-approved 2>&1 | tee -a "$LOG"

# Count how many reviewed examples have been added since last training run.
# Legacy raw chat remains in memory/finetune_dataset.jsonl for audit only.
LAST_ADAPTER=$(ls -dt "$BASE/memory/lora_adapters"/echo-soul-20* 2>/dev/null | head -1)
if [ -n "$LAST_ADAPTER" ]; then
    LAST_TRAINED=$(stat -c "%Y" "$LAST_ADAPTER")
    if [ ! -f "$DATASET" ]; then
        NEW_COUNT=0
    else
        NEW_COUNT=$(awk -v cutoff="$LAST_TRAINED" '
        {
            match($0, /"ts": *"([^"]+)"/, arr)
            if (arr[1] != "") {
                cmd = "date -d \"" arr[1] "\" +%s 2>/dev/null"
                cmd | getline ts
                close(cmd)
                if (ts+0 > cutoff+0) count++
            } else {
                count++
            }
        }
        END { print count+0 }
    ' "$DATASET" 2>/dev/null || wc -l < "$DATASET")
    fi
    log "New reviewed examples since last training: $NEW_COUNT"
    if [ "${NEW_COUNT:-0}" -lt 20 ]; then
        log "Not enough reviewed data (need 20+) — skipping training run"
        log "=== Fine-tune pipeline complete (no-op) ==="
        exit 0
    fi
else
    log "No previous adapter found — running first training"
fi

MIN_FREE_VRAM_MB="${ECHO_FINETUNE_MIN_FREE_VRAM_MB:-9000}"
if command -v nvidia-smi >/dev/null 2>&1; then
    FREE_VRAM_MB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
    if [ -n "${FREE_VRAM_MB:-}" ] && [ "$FREE_VRAM_MB" -lt "$MIN_FREE_VRAM_MB" ]; then
        log "GPU too busy for fine-tune: free_vram=${FREE_VRAM_MB}MB need=${MIN_FREE_VRAM_MB}MB — skipping training run"
        log "=== Fine-tune pipeline complete (gpu-busy no-op) ==="
        exit 0
    fi
    log "GPU preflight ok: free_vram=${FREE_VRAM_MB:-unknown}MB threshold=${MIN_FREE_VRAM_MB}MB"
else
    log "WARNING: nvidia-smi not found — continuing without GPU memory preflight"
fi

# Activate venv
if [ -f "$VENV/bin/activate" ]; then
    source "$VENV/bin/activate"
    log "Activated venv: $VENV"
else
    log "WARNING: venv not found at $VENV — using system Python"
fi

# Step 0: Keep legacy filter report for audit, but do not train on raw chat.
log "--- Step 0: Auditing legacy raw training set (not used for training) ---"
python3 "$BASE/tools/finetune_dataset_filter.py" 2>&1 | tee -a "$LOG"

# Step 0.5: Build the verified-reasoning dataset (the trainer prefers it once >=50
# traces exist — intelligence training, not just voice).
log "--- Step 0.5: Building verified-reasoning dataset ---"
python3 "$BASE/tools/build_reasoning_dataset.py" 2>&1 | tee -a "$LOG"

# Step 1: Train LoRA (reads verified reasoning or reviewed conversation examples)
log "--- Step 1: Training LoRA adapter ---"
python3 "$BASE/tools/finetune_train.py" 2>&1 | tee -a "$LOG"
TRAIN_EXIT=${PIPESTATUS[0]}
if [ "$TRAIN_EXIT" -ne 0 ]; then
    log "Training failed (exit $TRAIN_EXIT) — aborting"
    exit 1
fi

# Step 2: Merge + GGUF + Ollama
log "--- Step 2: Merging, converting, loading into Ollama ---"
python3 "$BASE/tools/finetune_export.py" 2>&1 | tee -a "$LOG"
EXPORT_EXIT=${PIPESTATUS[0]}
if [ "$EXPORT_EXIT" -ne 0 ]; then
    log "Export failed (exit $EXPORT_EXIT)"
    exit 1
fi

log "=== Fine-tune pipeline complete: $TIMESTAMP ==="
