#!/bin/bash
echo "Switching to High Performance Mode..."
powerprofilesctl set performance  # Or your power tool: cpupower frequency-set -g performance
start_golem.sh
echo "High Perf: Golem on, max power. Active session? y/N"; read ans; [ "$ans" = "y" ] && stop_session.sh
notify-send "High Perf Mode Active" "GPU/CPU maxed for content day."
