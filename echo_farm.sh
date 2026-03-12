#!/bin/bash
cd ~/Echo
watch -n 30 '
echo "=== $(date) ECHO FARM ==="
systemctl --user status echo --no-pager | grep Active || echo "Restart: systemctl restart echo"
tail -1 golem_pure.json | jq .glml 2>/dev/null || echo 0
wc -l echo_memory.json
ps aux | grep -c "agent\|monitor\|streamlit"
curl -s localhost:3000 | grep -c "GLM\|Echo"
yagna payment status --precise | grep GLM
journalctl -u echo -n3 | tail -1
'
