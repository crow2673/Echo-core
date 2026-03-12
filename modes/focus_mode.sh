#!/bin/bash
echo "$(date) — Entered Focus Mode" >> ~/Echo/memory/mode_history.log
echo "Switching to Focus Mode..."

# CPU: balanced (stable)
powerprofilesctl set balanced

# Disable reminders
rm -f ~/.echo_reminders_enabled

notify-send "Echo" "Focus Mode activated. Notifications minimized."
echo "Focus Mode activated."
