#!/bin/bash
echo "$(date) — Entered Low Power Mode" >> ~/Echo/memory/mode_history.log
echo "Switching to Low Power Mode..."

# CPU: powersave
powerprofilesctl set power-saver

# Stop Golem
~/Echo/stop_golem.sh

# Disable reminders
rm -f ~/.echo_reminders_enabled

# Auto-stop any active session
if [ -f "$HOME/Echo/memory/current_session.txt" ]; then
  "$HOME"/Echo/stop_session.sh
else
  echo "Low Power Mode: no active session to stop."
fi

notify-send "Echo" "Low Power Mode activated."
echo "Low Power Mode activated."
