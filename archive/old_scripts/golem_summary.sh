#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/.local/share/ya-provider/ya-provider_rCURRENT.log"
if [[ ! -f "$LOG" ]]; then
  echo "No provider log yet: $LOG"
  exit 0
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# High-signal keywords, hide common expiration noise
grep -Ei 'task|agreement|invoice|debit|payment|paid|earning|earn|allocated|accepted|confirmed|processing|running|started|error|warn' "$LOG" \
  | grep -Ev '410 Gone|Subscription 
$$
.*
$$ expired|Can.t unsubscribe expired Offer|Failed to unsubscribe offers from the market:.*410 Gone|market events.*404 Not Found; msg: .*expired' \
  | tail -120 > "$TMP" || true

if [[ -s "$TMP" ]]; then
  cat "$TMP"
  exit 0
fi

echo "(No high-signal events yet: no tasks/agreements/payments logged.)"
echo
echo "Recent WARN/ERROR (filtered):"
grep -Ei 'warn|error' "$LOG" \
  | grep -Ev '410 Gone|Subscription 
$$
.*
$$ expired|Can.t unsubscribe expired Offer|market events.*404 Not Found; msg: .*expired' \
  | tail -25 || true
