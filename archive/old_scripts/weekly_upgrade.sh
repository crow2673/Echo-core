#!/bin/bash
echo "--- Echo Weekly Maintenance ---"
# 1. Backup Memory
cp echo_memory.json backup_echo_memory.json
# 2. Clear old logs
echo "" > control_center.log
echo "" > nohup.out
# 3. Run Doctor
./echo_doctor.sh
# 4. Sync Finances
python3 echo_sync_finances.py
echo "[+] Maintenance Complete. System is optimized."
