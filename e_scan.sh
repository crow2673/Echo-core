#!/bin/bash
echo "=== ECHO AI SCAN ($(date)) ==="
echo "Processes (echo/ollama/python):"
ps aux | grep -E "ollama serve|ollama runner|python3 .*echo_agi_lite\.py|python3 .*gai_ramp\.py|python3 .*dashboard_ai\.py|screen -S echowatch" | grep -v grep | head -15
echo "Resource Spy:"
free -h | head -3; df -h ~/ | tail -1; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits -i 0 || echo "No GPU"
echo "Vision Screens:"
ls -lt ~/Echo/screen_*.png | head -5 | awk '{print $9" "$6,$7,$8}'
echo "Memory Files:"
du -sh ~/Echo/{echo_memory.json,archives/*.json,*.log} 2>/dev/null | head -10
echo "Ollama Live:"
ollama ps 2>/dev/null | sed -n '1,10p' || echo "Ollama down?"
echo "AI Logs Tail:"
tail -3 ~/Echo/{echo_agi_lite.log,echo_activity.log,ocr.log} 2>/dev/null || echo "Logs quiet"
echo "Self-Act PIDs:"
pgrep -f 'echo_agi_lite\|gai_ramp\|dashboard' || echo "No AI loops"
echo "=== END AI SCAN ==="
