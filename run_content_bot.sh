#!/usr/bin/env bash
set -euo pipefail

ECHO_DIR="$HOME/Echo"
BOT_DIR="$("$ECHO_DIR/echo_state_get.sh" paths.content_bot_dir)"
PYBIN="$("$ECHO_DIR/echo_state_get.sh" paths.content_bot_python)"

export DAILY_ENFORCE="${DAILY_ENFORCE:-1}"
export CONTENT_LIMIT="${CONTENT_LIMIT:-1}"
export MODEL_TIMEOUT="${MODEL_TIMEOUT:-1800}"

echo "Running content pipeline..."
echo "BOT_DIR=$BOT_DIR"
echo "PYBIN=$PYBIN"

cd "$BOT_DIR"

marker="$(mktemp)"
trap 'rm -f "$marker"' EXIT
touch "$marker"

# 1) Generate (1/day enforced inside generate_content.py)
"$PYBIN" generate_content.py

# 2) Collect new drafts from this run
mapfile -t new_drafts < <(find "$BOT_DIR/drafts" -maxdepth 1 -type f -name '*.md' -newer "$marker" -printf '%f\n' | sort)

if [[ "${#new_drafts[@]}" -eq 0 ]]; then
  echo "No new drafts generated; skipping refine + queue."
  exit 0
fi

echo "New draft(s):"
printf '  - %s\n' "${new_drafts[@]}"

# 3) Refine only those drafts (total wall time bound)
echo "Refining new draft(s)..."
timeout 35m "$PYBIN" refine_content.py "${new_drafts[@]}" || echo "Refine timed out/failed; continuing."

# 4) Queue for publishing (simple JSON job per refined file)
mkdir -p "$BOT_DIR/queue" "$BOT_DIR/published"

export BOT_DIR
export NEW_DRAFTS="$(printf '%s\n' "${new_drafts[@]}")"

python3 - <<'PY'
import json, os, re
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo

BOT_DIR = Path(os.environ["BOT_DIR"])
new_drafts = [l.strip() for l in os.environ["NEW_DRAFTS"].splitlines() if l.strip()]

refined_dir = BOT_DIR / "refined_drafts"
queue_dir = BOT_DIR / "queue"
queue_dir.mkdir(parents=True, exist_ok=True)

tz = zoneinfo.ZoneInfo("America/Chicago")  # change if needed
now = datetime.now(tz)

def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return re.sub(r'-+', '-', s).strip('-')[:80]

# Simple schedule rule: next publish slot = tomorrow 09:30 if already past 09:30 today
publish_at = now.replace(hour=9, minute=30, second=0, microsecond=0)
if publish_at <= now:
    publish_at = publish_at + timedelta(days=1)

for fn in new_drafts:
    refined_path = refined_dir / fn
    source = refined_path if refined_path.exists() else (BOT_DIR / "drafts" / fn)

    title = Path(fn).stem.replace("_", " ")
    job = {
        "id": f"{publish_at.strftime('%Y%m%d-%H%M')}-{slug(title)}",
        "title": title,
        "source_file": str(source),
        "publish_at": publish_at.isoformat(),
        "status": "queued",
        "platform": "TBD"
    }
    out = queue_dir / f'{job["id"]}.json'
    out.write_text(json.dumps(job, indent=2) + "\n")
    print(f"Queued: {out}")
PY

echo "Content pipeline finished."
