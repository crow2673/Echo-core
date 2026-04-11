#!/usr/bin/env python3
"""Regenerate echo_contract.json with current state."""
import json, sqlite3, hashlib, requests
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"

def md5(path):
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()
    except:
        return "missing"

def memory_count():
    try:
        c = sqlite3.connect(str(BASE / "echo_semantic_memory.sqlite"))
        n = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        c.close()
        return n
    except:
        return 0

def get_trading_status():
    try:
        env = {}
        for line in (Path.home() / ".config/echo/golem.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
        import alpaca_trade_api as tradeapi
        api = tradeapi.REST(env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"], env["ALPACA_BASE_URL"])
        account = api.get_account()
        portfolio = float(account.portfolio_value)
        gain = portfolio - 100000
        return {"portfolio": round(portfolio, 2), "gain": round(gain, 2)}
    except:
        return {"portfolio": 0, "gain": 0}

def get_crow_snapshot():
    try:
        resp = requests.post("http://127.0.0.1:8787/api/plaid/sync",
                           json={"days": 30}, timeout=15)
        if resp.status_code == 200:
            crow = resp.json().get("crow", {})
            return {
                "mode": crow.get("mode", "unknown"),
                "runway_days": crow.get("runway_days", 0),
                "monthly_net": crow.get("monthly_net", 0)
            }
    except:
        pass
    return {"mode": "unavailable", "runway_days": 0, "monthly_net": 0}

# Load existing contract
contract = json.loads((BASE / "echo_contract.json").read_text())

# Update timestamps and hashes
contract["updated_at"] = datetime.now().isoformat()
contract["memory"]["total_memories"] = memory_count()
contract["memory"]["memory_db_hash"] = md5(BASE / "echo_semantic_memory.sqlite")
contract["identity"]["modelfile_hash"] = md5(BASE / "Echo.Modelfile")

# Update mission context with live data
trading = get_trading_status()
crow = get_crow_snapshot()

contract["mission_context"]["updated"] = datetime.now().isoformat()
contract["mission_context"]["paper_trading_gain"] = trading["gain"]
contract["mission_context"]["household_mode"] = crow["mode"]
contract["mission_context"]["runway_days"] = crow["runway_days"]

# Save
(BASE / "echo_contract.json").write_text(json.dumps(contract, indent=2))
print(f"Contract updated v{contract['contract_version']}: {memory_count()} memories | portfolio gain ${trading['gain']:+,.2f} | household {crow['mode']} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
