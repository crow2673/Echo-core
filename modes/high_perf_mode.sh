#!/bin/bash
echo "$(date) — Entered High Performance Mode" >> ~/Echo/memory/mode_history.log
echo "Switching to High Performance Mode..."

# CPU: performance
powerprofilesctl set performance

# Stop Golem (avoid lag)
~/Echo/stop_golem.sh

# Disable reminders
rm -f ~/.echo_reminders_enabled

notify-send "Echo" "High Performance Mode activated."
echo "High Performance Mode activated."
