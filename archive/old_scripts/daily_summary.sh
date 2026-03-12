#!/bin/bash

echo "===== Echo Daily Summary ====="
echo ""

echo "Recent Activity:"
tail -n 20 ~/Echo/memory/activity.log
echo ""

echo "Recent Events:"
tail -n 20 ~/Echo/memory/events.log
echo ""

echo "Your Notes:"
cat ~/Echo/memory/log_notes.txt 2>/dev/null || echo "(no notes yet)"
echo ""

echo "==============================="
