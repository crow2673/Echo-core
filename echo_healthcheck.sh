#!/bin/bash
# Echo healthcheck — checks all critical services and reports status
PASS=0
FAIL=0
OUTPUT=""

check_user_service() {
    local name=$1
    # Try direct user check first, then try as andrew user
    if systemctl --user is-active "$name" &>/dev/null; then
        OUTPUT="$OUTPUT OK:$name"
        PASS=$((PASS+1))
    elif su -c "systemctl --user is-active $name" andrew &>/dev/null 2>&1; then
        OUTPUT="$OUTPUT OK:$name"
        PASS=$((PASS+1))
    else
        OUTPUT="$OUTPUT FAIL:$name"
        FAIL=$((FAIL+1))
    fi
}

check_timer() {
    local name=$1
    if systemctl list-timers --all 2>/dev/null | grep -q "$name" ||        systemctl --user list-timers --all 2>/dev/null | grep -q "$name" ||        [ -f "/etc/systemd/system/${name}.timer" ] ||        [ -f "/etc/systemd/user/${name}.timer" ]; then
        OUTPUT="$OUTPUT OK:$name"
        PASS=$((PASS+1))
    else
        OUTPUT="$OUTPUT FAIL:$name"
        FAIL=$((FAIL+1))
    fi
}

check_system_service() {
    local name=$1
    if systemctl is-active "$name" &>/dev/null; then
        OUTPUT="$OUTPUT OK:$name"
        PASS=$((PASS+1))
    else
        OUTPUT="$OUTPUT FAIL:$name"
        FAIL=$((FAIL+1))
    fi
}

# Persistent user services
check_user_service "echo-core"
check_user_service "echo-ntfy-bridge"

# System timers
check_timer "echo-governor"
check_timer "echo-self-act-worker"
check_timer "echo-rss-monitor"

# Ollama
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    OUTPUT="$OUTPUT OK:ollama"
    PASS=$((PASS+1))
else
    OUTPUT="$OUTPUT FAIL:ollama"
    FAIL=$((FAIL+1))
fi

# Golem — check yagna process directly
if pgrep -x yagna &>/dev/null; then
    OUTPUT="$OUTPUT OK:golem"
    PASS=$((PASS+1))
else
    OUTPUT="$OUTPUT FAIL:golem"
    FAIL=$((FAIL+1))
fi

# Disk space
DISK=$(df ~/Echo | awk 'NR==2{print $5}' | tr -d '%')
if [ "$DISK" -lt 85 ]; then
    OUTPUT="$OUTPUT OK:disk(${DISK}%)"
    PASS=$((PASS+1))
else
    OUTPUT="$OUTPUT WARN:disk(${DISK}%)"
    FAIL=$((FAIL+1))
fi

echo "healthcheck: $PASS passed $FAIL failed |$OUTPUT"
[ $FAIL -eq 0 ] && exit 0 || exit 1
