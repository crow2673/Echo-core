#!/usr/bin/env bash
set -euo pipefail

ECHO_DIR="$HOME/Echo"
BOT_DIR="$("$ECHO_DIR/echo_state_get.sh" paths.content_bot_dir)"
PYBIN="$("$ECHO_DIR/echo_state_get.sh" paths.content_bot_python)"

archive_dir="$ECHO_DIR/memory/archive_$(date +%Y%m%d-%H%M%S)"
mkdir -p "$archive_dir"

for f in activity.log events.log; do
  if [[ -f "$ECHO_DIR/memory/$f" ]]; then
    mv "$ECHO_DIR/memory/$f" "$archive_dir/$f"
  fi
  : > "$ECHO_DIR/memory/$f"
done

echo "Archived old logs to $archive_dir"

marker="$(mktemp)"
trap 'rm -f "$marker"' EXIT
touch "$marker"

# 1) Generate new drafts
"$ECHO_DIR/run_content_bot.sh"

# 2) Find drafts created/updated since marker
mapfile -t new_drafts < <(find "$BOT_DIR/drafts" -maxdepth 1 -type f -name '*.md' -newer "$marker" -printf '%f\n' | sort)

if [[ "${#new_drafts[@]}" -eq 0 ]]; then
  echo "No new drafts since this run. Skipping refine/analyze."
  echo "Weekly upgrade complete!"
  exit 0
fi

echo "New drafts this run:"
printf '  - %s\n' "${new_drafts[@]}"

# 3) Refine only those new drafts, time-bounded
# Adjust MODEL_TIMEOUT (per-request) + timeout (total wall time) as needed
export MODEL_TIMEOUT="${MODEL_TIMEOUT:-180}"
timeout 25m "$PYBIN" "$BOT_DIR/refine_content.py" "${new_drafts[@]}" || \
  echo "Refine step timed out or failed; continuing."

# 4) Analyze (also time-bounded so upgrade never hangs)
timeout 10m python3 "$ECHO_DIR/analyze_content.py" || \
  echo "Analyze step timed out or failed; continuing."

echo "Weekly upgrade complete!"
