#!/bin/bash
# Echo Control Center v1.1 — Fixed for Ubuntu 24.04 venv

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

source ~/Echo/venv/bin/activate  # Always use venv
VENV_PYTHON=$(which python)

DAEMON_PID=$(pgrep -f "echo_daemon_loop.py")
SELF_PID=$(pgrep -f "self_act.py")

echo_daemon_status() {
  if [ -n "$DAEMON_PID" ]; then echo -e "${GREEN}✓ echo_daemon_loop.py (PID $DAEMON_PID) UP${NC}"; return 0; else echo -e "${RED}✗ echo_daemon_loop.py DOWN${NC}"; return 1; fi
}

self_act_status() {
  if [ -n "$SELF_PID" ]; then echo -e "${GREEN}✓ self_act.py (PID $SELF_PID) UP${NC}"; return 0; else echo -e "${RED}✗ self_act.py DOWN${NC}"; return 1; fi
}

case "$1" in
  status)
    echo "=== Echo Status ==="
    echo_daemon_status; self_act_status
    echo "Key Ports:"
    ss -tulpn | grep LISTEN | grep -E '7465|631' | head -3  # Yagna + yours
    echo "Logs tail:"
    tail -5 daemon.log self_act.log 2>/dev/null || echo "No logs yet"
    echo "Hit htop/glances for more"
    ;;
  start)
    cd ~/Echo
    if [ -z "$DAEMON_PID" ]; then nohup $VENV_PYTHON echo_daemon_loop.py > daemon.log 2>&1 & echo -e "${GREEN}✓ Daemon PID $!${NC}"; fi
    if [ -z "$SELF_PID" ]; then nohup $VENV_PYTHON core/self_act.py > self_act.log 2>&1 & echo -e "${GREEN}✓ SelfAct PID $!${NC}"; fi
    ;;
  stop)
    [ -n "$DAEMON_PID" ] && kill $DAEMON_PID 2>/dev/null && echo -e "${GREEN}Stopped daemon${NC}" || true
    [ -n "$SELF_PID" ] && kill $SELF_PID 2>/dev/null && echo -e "${GREEN}Stopped self_act${NC}" || true
    ;;
  restart) bash $0 stop && sleep 2 && bash $0 start ;;
  logs) tail -f daemon.log self_act.log 2>&1 ;;
  dev) honcho start ;;  # Procfile mode
  tmx)
    tmux new-session -d -s Echo -c ~/Echo
    tmux send-keys -t Echo:0.0 "bash echo-hub.sh status" C-m
    tmux split-window -h -t Echo:0
    tmux send-keys -t Echo:0.1 "tail -f *.log" C-m
    tmux split-window -v -t Echo:0.1
    tmux send-keys -t Echo:0.2 "htop" C-m
    tmux attach -t Echo
    ;;
  *) echo "Usage: bash echo-hub.sh {status|start|stop|restart|logs|dev|tmx}"; echo_daemon_status; self_act_status ;;
esac
deactivate  # Clean exit
