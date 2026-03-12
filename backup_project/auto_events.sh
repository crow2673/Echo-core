#!/bin/bash

timestamp=$(date "+%Y-%m-%d %H:%M:%S")

journalctl -p err -n 5 --no-pager > /tmp/echo_errors.txt

echo "[$timestamp]" >> ~/Echo/memory/events.log
cat /tmp/echo_errors.txt >> ~/Echo/memory/events.log
echo "----" >> ~/Echo/memory/events.log
