#!/bin/bash
echo "=== ECHO HEALTH SCAN ($(date)) ==="
echo "--- Uptime/Date Fix? ---"
uptime; date
echo "--- Processes (echo|yagna|golem|ollama) ---"
ps aux | grep -E 'echo|yagna|golem|ollama' | grep -v grep | head -15
echo "--- Top CPU/Mem (Echo-related) ---"
PIDS=$(pgrep -f 'ollama|echo_|yagna'); top -b -n1 -p $PIDS | head -25 || echo "No PIDs"
echo "--- Payments/Offers ---"
yagna payment status --network polygon 2>/dev/null || echo "yagna offline"
echo "--- Provider Status ---"
systemctl --user status golem-provider.service --no-pager -l 2>/dev/null || echo "systemctl fail"
echo "--- Ollama Status ---"
ollama ps 2>/dev/null || echo "ollama offline"
echo "--- Quick Fixes ---"
echo "Run: pkill -f 'echo_simple_agent.py'; pkill -f 'echo_daemon_loop.py'"
