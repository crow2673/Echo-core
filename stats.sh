#!/bin/bash
cpu=$(grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}')
gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null)
ram=$(free -h | grep Mem | awk '{print $3 "/" $2}')
echo "CPU Usage: $cpu%"
echo "GPU Usage: ${gpu:-N/A}"
echo "RAM Usage: $ram"
