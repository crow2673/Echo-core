#!/bin/bash
# Auto-stop Echo session if you've been idle too long.

SESSION_FILE="$HOME/Echo/memory/current_session.txt"

# No active session → nothing to do
if [ ! -f "$SESSION_FILE" ]; then
  exit 0
fi

# Get idle time in ms (xprintidle), default to 0 if unavailable
idle_ms=$(xprintidle 2>/dev/null || echo 0)

# Threshold: 45 minutes of idle time
threshold_ms=$((45 * 60 * 1000))

if [ "$idle_ms" -gt "$threshold_ms" ]; then
  # Optional: desktop notification
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Echo" "Auto-ending session after $(($idle_ms / 60000)) minutes of idle time."
  fi

  "$HOME"/Echo/stop_session.sh
fi
