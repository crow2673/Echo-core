#!/bin/bash
timestamp=$(date "+%Y-%m-%d %H:%M:%S")
echo "$timestamp,START,Income" >> ~/Echo/memory/time_log.csv
echo "Income|$timestamp" > ~/Echo/memory/current_session.txt
echo "Started Income session at $timestamp"
