#!/bin/bash
echo "$(date),end,,$(date +%s),$1" >> memory/time_log.csv  # Session end
notify-send "Session Ended" "Logged: $1"
read -p "Quick notes? (posts/views/golem): " notes
echo "$(date),notes,$notes" >> memory/time_log.csv
