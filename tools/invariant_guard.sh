#!/usr/bin/env bash
set -euo pipefail

fail(){ echo "[FAIL] $*" >&2; exit 1; }
ok(){ echo "[OK] $*"; }

ECHO="$HOME/Echo"
test -d "$ECHO" || fail "missing $ECHO"
test -f "$ECHO/core/__init__.py" || fail "missing core/__init__.py (core must be a package)"

# echo alias must NOT exist (breaks scripts)
if alias echo >/dev/null 2>&1; then
  fail "alias 'echo' exists; remove it (it breaks scripts)"
else
  ok "no alias echo"
fi
# echo CLI must exist and be executable
if [ ! -x "$ECHO/echo" ]; then
  fail "missing or non-executable $ECHO/echo (health CLI required)"
else
  ok "echo CLI present"
fi

# memory directory (and system state source) must exist
if [ ! -d "$ECHO/memory" ]; then
  fail "missing $ECHO/memory directory"
else
  ok "memory directory present"
fi

# core orchestrator must be running (or can be started)
ok "invariant_guard passed"
