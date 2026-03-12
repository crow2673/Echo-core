# Echo Architecture Invariants
ARCH_INVARIANTS_VERSION: 0.7

This file defines **non-negotiable invariants** for Echo’s runtime architecture so future refactors do not reintroduce packaging/systemd ambiguity or duplicate loops.

## 1) Single Orchestrator Principle
- **echo-core.service** is the sole long-lived orchestrator.
- All other work is performed via **oneshot workers** + timers.
- Never run multiple “core loops” that compete for the same queues/logs.

**Current orchestrator**
- systemd unit: `echo-core.service`
- Exec: `~/Echo/venv/bin/python3 -u ~/Echo/echo_core_daemon.py`

## 2) Worker Pattern (Deterministic)
Workers must be:
- `Type=oneshot`
- Idempotent per run
- Deterministic queue handling (consume → process → clear/commit)

**self_act worker**
- unit: `echo-self-act-worker.service`
- Exec: `python3 -m core.self_act --once`
- Output: appends to `~/Echo/memory/self_act.log`

## 3) Python Packaging Invariant
- `~/Echo/core/` is a **real Python package**:
  - `~/Echo/core/__init__.py` must exist.
- All package-internal imports use **relative imports**:
  - Example: `from .gpt_reasoner import gpt_reasoner`
- When running modules, prefer:
  - `python3 -m core.self_act` (NOT `python3 core/self_act.py`)

This prevents “attempted relative import with no known parent package” and makes systemd execution deterministic.

## 4) State File Invariants
Canonical health snapshot:
- `~/Echo/memory/core_state_system.json`

Reasoning state:
- `~/Echo/memory/core_state_reasoning.json`

Rules:
- `core_state_system.json` is **read-only to workers** (workers consume status; core-state writer owns updates).
- Workers must not invent facts; they can only summarize what’s present.

## 5) Health Command Invariant
A single health command must exist and must be stable:
- `~/Echo/echo status` reads `core_state_system.json` and prints:
  - core service status
  - key services/timers
  - last pulse + last command
  - any errors

## 6) Shell Safety Invariant (Critical)
Do **not** alias `echo` to anything. It breaks scripts.
Use `alias echoroot='cd ~/Echo'` instead.

