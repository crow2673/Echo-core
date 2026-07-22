#!/usr/bin/env bash
# Keep Claude + Codex available in tmux so Echo's conductor can wake them.
set -euo pipefail

ACTION="${1:---ensure}"
SESSION="${ECHO_AGENT_SESSION:-echo-agents}"
BASE="${ECHO_BASE:-/home/andrew/Echo}"
CLAUDE_CMD="${CLAUDE_CMD:-/home/andrew/.local/bin/claude}"
CODEX_CMD="${CODEX_CMD:-/home/andrew/.local/bin/codex}"
LOCK_FILE="${ECHO_AGENT_LOCK:-$BASE/memory/.launch_agents.repair.lock}"

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -w 40 9

has_session() {
  tmux has-session -t "$SESSION" 2>/dev/null
}

window_target() {
  local name="$1"
  tmux list-panes -a -F '#{session_name} #{window_name} #{session_name}:#{window_index}.#{pane_index} #{pane_dead}' |
    awk -v session="$SESSION" -v wanted="$name" '$1 == session && $2 == wanted && $4 == "0" {print $3; exit}'
}

window_exists() {
  [[ -n "$(window_target "$1")" ]]
}

launch_window() {
  local name="$1"
  local command="$2"
  if [[ ! -x "$command" ]]; then
    echo "agent command is not executable: $command" >&2
    return 1
  fi
  if ! has_session; then
    tmux new-session -d -s "$SESSION" -n "$name" -c "$BASE" "$command" 9>&-
  else
    tmux new-window -d -t "$SESSION:" -n "$name" -c "$BASE" "$command" 9>&-
  fi
}

register_agents() {
  local claude_target codex_target
  claude_target="$(window_target claude)"
  codex_target="$(window_target codex)"
  [[ -n "$claude_target" ]] && python3 "$BASE/core/conductor.py" --register claude "$claude_target"
  [[ -n "$codex_target" ]] && python3 "$BASE/core/conductor.py" --register codex "$codex_target"
  [[ -n "$claude_target" && -n "$codex_target" ]]
}

ensure_agents() {
  local attempt
  if ! window_exists claude; then
    launch_window claude "$CLAUDE_CMD"
  fi
  if ! window_exists codex; then
    launch_window codex "$CODEX_CMD"
  fi
  for attempt in {1..20}; do
    if register_agents; then
      return 0
    fi
    sleep 1
  done
  echo "agents did not become ready within 20 seconds" >&2
  return 1
}

status() {
  if ! has_session; then
    echo "session '$SESSION' is absent"
    return 1
  fi
  tmux list-panes -a -F '#{session_name} #{window_name} #{session_name}:#{window_index}.#{pane_index} command=#{pane_current_command} dead=#{pane_dead}' |
    awk -v session="$SESSION" '$1 == session {$1=""; sub(/^ /, ""); print}'
  python3 "$BASE/core/conductor.py" --list
}

case "$ACTION" in
  --ensure)
    ensure_agents
    ;;
  --register)
    register_agents
    ;;
  --status)
    status
    ;;
  --stop)
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    ;;
  *)
    echo "Usage: $0 [--ensure|--register|--status|--stop]" >&2
    exit 2
    ;;
esac
