#!/usr/bin/env python3
import subprocess
import csv
import datetime
import re

# Path to log file
log_file = "memory/golem_log.csv"

# Ensure the memory directory exists
import os
os.makedirs(os.path.dirname(log_file), exist_ok=True)

# Run the yagna payment status command
try:
    result = subprocess.run(["yagna", "payment", "status"], capture_output=True, text=True)

    # Parse the output
    output = result.stdout
    match = re.search(r"total amount\s+\|\s+([\d\.]+)\s+tGLM", output)
    
    if match:
        total_amount = float(match.group(1))
    else:
        total_amount = 0

    # Log the result
    with open(log_file, "a", newline='') as f:
        writer = csv.writer(f)

        # Add a timestamp and total amount
        run_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([run_date, total_amount])

    print(f"Golem earnings logged: {total_amount} tGLM")

except Exception as e:
    print(f"Error checking Golem status: {e}")
