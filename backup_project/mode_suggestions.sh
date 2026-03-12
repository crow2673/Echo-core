#!/bin/bash
# Suggest an Echo mode based on current load and time

hour=$(date +%H)
idle_ms=$(xprintidle 2>/dev/null || echo 0)

# CPU usage
cpu=$(grep 'cpu ' /proc/stat | \
  awk '{usage=($2+$4)*100/($2+$4+$5)} END {printf "%.0f", usage}')

# GPU usage (if NVIDIA present)
gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | tr -dc '0-9')

suggestion="Focus Mode"

# High load → High Performance
if [ "$cpu" -gt 80 ] || { [ -n "$gpu" ] && [ "$gpu" -gt 80 ]; }; then
  suggestion="High Performance Mode"
# Work hours & active → Workday
elif [ "$hour" -ge 9 ] && [ "$hour" -le 18 ] && [ "$idle_ms" -lt 1800000 ]; then
  suggestion="Workday Mode"
# Late or long idle → Low Power
elif [ "$hour" -ge 22 ] || [ "$idle_ms" -gt 3600000 ]; then
  suggestion="Low Power Mode"
fi

echo "Suggested: $suggestion (CPU: ${cpu}%, GPU: ${gpu:-N/A}, hour: $hour, idle_ms: $idle_ms)"

# Desktop notification if available
if command -v notify-send >/dev/null 2>&1; then
  notify-send "Echo Mode Suggestion" "Suggested: $suggestion"
fi

# Log suggestion
echo "$(date "+%Y-%m-%d %H:%M:%S"),$suggestion,CPU=${cpu}%,GPU=${gpu:-N/A},hour=$hour,idle_ms=$idle_ms" \
  >> "$HOME/Echo/memory/mode_history.log"
