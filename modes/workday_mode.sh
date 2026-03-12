#!/bin/bash
echo "$(date) — Entered Workday Mode" >> ~/Echo/memory/mode_history.log
echo "Switching to Workday Mode..."

# CPU: performance
powerprofilesctl set performance

# Start Golem
~/Echo/start_golem.sh

# Open Outlier
xdg-open https://app.outlier.ai &

# Enable reminders
touch ~/.echo_reminders_enabled

# Auto-start Income session if none active
if [ ! -f "$HOME/Echo/memory/current_session.txt" ]; then
  "$HOME"/Echo/start_income.sh
else
  echo "Workday Mode: existing session detected, not auto-starting Income."
fi

notify-send "Echo" "Workday Mode activated."
echo "Workday Mode activated."
