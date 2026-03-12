#!/bin/bash
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir=~/Echo_Backups
mkdir -p $backup_dir
tar -czf $backup_dir/Echo_backup_$timestamp.tar.gz ~/Echo
echo "Echo backed up to $backup_dir/Echo_backup_$timestamp.tar.gz"
