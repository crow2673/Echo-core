#!/bin/bash
set -e
echo "== Echo + Golem Healthcheck =="
echo "-- golem-provider.service:"
systemctl --user is-enabled golem-provider.service
systemctl --user is-active golem-provider.service
systemctl --user status golem-provider.service -l --no-pager | sed -n '1,14p'
echo
echo "-- yagna auth:"
source "$HOME/.config/echo/golem.env"
curl -sS -m 2 -H "Authorization: Bearer $YAGNA_APPKEY" http://127.0.0.1:7465/me
echo
echo "-- provider log tail:"
tail -10 "$HOME/.local/share/ya-provider/ya-provider_rCURRENT.log" 2>/dev/null || true
