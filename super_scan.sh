#!/bin/bash
echo "=== GAI SUPER SCAN ==="
echo "HW/CPU": nproc && lscpu | grep -E "Model|MHz|Cache"
echo "Disk": df -h /
echo "Mem": free -h
echo "Net": ip a show | grep inet && ss -tuln | head -5
echo "Files": ls -la ~ | head -10; du -sh ~/Echo
echo "Procs": ps aux --sort=-%cpu | head -10
echo "Users": who; w | head -3
echo "History": history 5
echo "Payments": yagna payment status --precise
echo "Golem": systemctl --user status golem-provider -l | head -5
