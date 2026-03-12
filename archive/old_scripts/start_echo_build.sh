#!/bin/bash
timestamp=$(date "+%Y-%m-%d %H:%M:%S")
echo "$timestamp,START,EchoBuild" >> ~/Echo/memory/time_log.csv
echo "EchoBuild|$timestamp" > ~/Echo/memory/current_session.txt
echo "Started Echo-build session at $timestamp"
