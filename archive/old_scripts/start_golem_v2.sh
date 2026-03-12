#!/bin/bash
LOG_DIR="$HOME/Echo/memory"
mkdir -p "$LOG_DIR"
ACTIVITY_LOG="$LOG_DIR/activity.log"
CSV_LOG="$LOG_DIR/provider_status.csv"
PROVIDER_LOG="$LOG_DIR/provider.log"
log() { echo "$(date): $1" | tee -a "$ACTIVITY_LOG"; }
APP_KEY_FILE=$(cat "$LOG_DIR/app_key.path" 2>/dev/null || ls ~/.local/share/yagna/*.json | grep provider | head -1 || ls ~/.local/share/yagna/*.json | tail -1)
PROVIDER_KEYS="~/.local/share/yagna/provider_keys.json"

# Start/wait yagna service
log "Starting yagna service..."
for i in {1..30}; do
    if [ -S /tmp/yagna.sock ] || pgrep yagna; then
        log "Service ready ($i/30)."
        break
    fi
    sleep 1
done

# Provider init if needed
[ ! -f "$PROVIDER_KEYS" ] && yagna provider init --hardware cpu.x86-64-v1,intel-aes-v1 --subnet-id community.1

# Launch provider
log "Launching provider with app-key: $APP_KEY_FILE"
nohup yagna provider run \
  --api-key-path "$PROVIDER_KEYS" \
  --app-key-file "$APP_KEY_FILE" \
  --log-config-ya-provider=/dev/stderr \
  > "$PROVIDER_LOG" 2>&1 &
PROVIDER_PID=$!
echo $PROVIDER_PID > "$LOG_DIR/provider.pid"
log "PID: $PROVIDER_PID | Logs: $PROVIDER_LOG"
echo "$(date),Running,$PROVIDER_PID,$APP_KEY_FILE" >> "$CSV_LOG"

# Restart watcher
( while kill -0 $PROVIDER_PID 2>/dev/null; do sleep 30; done && log "Restarting..." && exec "$0"; ) &
