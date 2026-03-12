#!/usr/bin/env bash
set -euo pipefail
STATE_FILE="$(dirname "$0")/echo_state.json"

KEY="${1:-}"
if [[ -z "$KEY" ]]; then
  echo "Usage: $0 <dot.path.key>  (e.g. current_focus.primary_goal)"
  exit 2
fi

python3 - "$STATE_FILE" "$KEY" <<'PY'
import json,sys
path=sys.argv[2].split(".")
data=json.load(open(sys.argv[1]))
cur=data
for p in path:
    if isinstance(cur, dict) and p in cur:
        cur=cur[p]
    else:
        print("")
        sys.exit(1)
if isinstance(cur,(dict,list)):
    import json as j
    print(j.dumps(cur, indent=2))
else:
    print(cur)
PY
