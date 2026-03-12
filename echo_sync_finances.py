import json
import time
from pathlib import Path
from robinhood_adapter import RobinhoodAdapter
import robin_stocks.robinhood as r

MEMORY_FILE = Path("echo_memory.json")

def sync():
    adapter = RobinhoodAdapter()
    if not adapter.login(): return

    profile = r.build_user_profile()
    equity = profile.get('equity', '0.00')
    power = profile.get('buying_power', '0.00')

    crypto_positions = r.crypto.get_crypto_positions()
    crypto_report = []
    
    for pos in crypto_positions:
        qty = float(pos['quantity'])
        if qty > 0:
            symbol = pos['currency']['code']
            price_data = r.crypto.get_crypto_quote(symbol)
            current_price = float(price_data['mark_price'])
            value = qty * current_price
            crypto_report.append(f"{symbol}: ${value:.2f}")

    if MEMORY_FILE.exists():
        memory = json.loads(MEMORY_FILE.read_text())
        for cap in memory:
            if "Finance" in cap.get("capsule_id", ""):
                cap["status"] = "done"
                cap["verified"] = True
                report = f"Equity: ${equity} | Power: ${power} | Assets: {', '.join(crypto_report)}"
                cap.setdefault("result_notes", []).append(f"[{time.ctime()}] {report}")
        MEMORY_FILE.write_text(json.dumps(memory, indent=2))
        print(f"Finance Sync Complete: Equity ${equity}")

if __name__ == "__main__":
    sync()
