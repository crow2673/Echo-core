#!/usr/bin/env bash

STATE_FILE="$(dirname "$0")/echo_state.json"

if [ ! -f "$STATE_FILE" ]; then
  echo "Echo state file not found."
  exit 1
fi

echo "Echo state loaded:"
cat "$STATE_FILE"
