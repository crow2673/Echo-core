#!/bin/bash
set -u
ECHO_DIR="$HOME/Echo"
echo "== Echo Doctor =="
echo "-- Missing scripts (expected by panel):"
for f in daily_summary.sh stats.sh weekly_upgrade.sh open_outlier.sh cleanup.sh backup.sh modes.sh content_bot.sh workspace.sh publish_devto.sh gpu_monitor.sh monitor_earnings.sh start_provider.sh stop_provider.sh; do
  [[ -e "$ECHO_DIR/$f" ]] || echo "MISSING: $ECHO_DIR/$f"
done
echo
echo "-- Executable scripts (should be +x):"
for f in "$ECHO_DIR"/*.sh; do [[ -f "$f" ]] && [[ -x "$f" ]] || true; done
echo
echo "-- golem-provider.service:"
systemctl --user status golem-provider.service -l --no-pager || true
