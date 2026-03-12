#!/usr/bin/env bash
set -euo pipefail
STATE_FILE="$(dirname "$0")/echo_state.json"

python3 - <<PY
import json,sys
p="$STATE_FILE"
with open(p,"r",encoding="utf-8") as f:
    json.load(f)
print("OK: valid JSON ->", p)
PY
