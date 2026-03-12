#!/usr/bin/env python3
import json, subprocess, datetime, pathlib, sys, re

STATE_PATH = pathlib.Path.home() / "Echo/memory/core_state_system.json"

def sh(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def main():
    # Pull current yagna net status
    out = sh(["yagna", "net", "status"])
    m = re.search(r"^publicAddress:\s*(.+)$", out, flags=re.M)
    public_addr = (m.group(1).strip() if m else "null")

    # Normalize
    is_public = public_addr.lower() != "null" and public_addr != ""
    now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    # Load state JSON
    data = json.loads(STATE_PATH.read_text())

    net = data.get("network", {})
    net["mode"] = "public" if is_public else "relay"
    net["public_ipv4"] = bool(is_public)
    net["public_address"] = public_addr if is_public else None
    net["udp_11500_forwarded"] = bool(is_public)   # practical indicator in your setup
    net["verified_at"] = now
    net["note"] = "Auto-updated from `yagna net status`."

    data["network"] = net
    data["updated_at"] = now

    STATE_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
    print(f"OK updated network -> {net['mode']} {net.get('public_address')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
