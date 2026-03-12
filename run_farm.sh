#!/bin/bash
cd ~/Echo
watch -n 60 '
echo "=== $(date) GLM FARM ==="
systemctl --user status echo.service | grep Active || systemctl --user restart echo.service
tail -1 golem_pure.json | jq .glml 2>/dev/null || echo "0.0000"
wc -l echo_memory.json
ps aux | grep -c "golem\|monitor\|streamlit\|echo"
~/.local/bin/yagna provider status | head -5
journalctl --user -u golem-provider -n 3
tail -1 golem_pure.json
'
