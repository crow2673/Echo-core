#!/bin/bash
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir=~/Echo_Backups
mkdir -p $backup_dir
tar -czf $backup_dir/Echo_backup_$timestamp.tar.gz ~/Echo
echo "Echo backed up to $backup_dir/Echo_backup_$timestamp.tar.gz"

# Regenerate identity contract on every backup
python3 /home/andrew/Echo/core/update_contract.py 2>/dev/null && echo "Contract updated"


# Rotate logs before backup
python3 /home/andrew/Echo/core/log_rotator.py 2>/dev/null
