from micro_safe_trading_bot_live import MicroSafeTradingBotLive
from screen_watcher_adapter import ScreenWatcherAdapter
import time
import json
import os

# -------------------------
# Configuration
# -------------------------
STARTING_CAPITAL = 20.0
MIN_BUFFER = 2.0
MAX_FRACTION = 0.5
PROFIT_FACTOR = 0.05
TRADE_FEE = 0.2
SCREEN_REGION = (0, 0, 800, 600)  # Adjust to your platform screen area
LOG_FILE = "micro_safe_trade_log.json"

# -------------------------
# Initialize Bot & Adapter
# -------------------------
bot = MicroSafeTradingBotLive(
    capital=STARTING_CAPITAL,
    min_buffer=MIN_BUFFER,
    max_fraction=MAX_FRACTION,
    profit_factor=PROFIT_FACTOR
)

adapter = ScreenWatcherAdapter(region=SCREEN_REGION, fee=TRADE_FEE)

# -------------------------
# Load existing log if exists
# -------------------------
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r") as f:
        bot.trade_log = json.load(f)

print("Starting Live Screen-Watched MicroSafe Trading Bot...")

try:
    while True:
        # 1. Capture trades from screen
        trades = adapter.get_trades()

        # 2. Evaluate each trade
        results = bot.run_echo_feed(trades)

        # 3. Print and log results
        for r in results:
            t = r["trade"]
            status = "APPROVED ✅" if r["approved"] else "REJECTED ❌"
            print(f"Trade {t} -> {status} | Current Capital: ${bot.capital:.2f}")

        # 4. Save trade log
        with open(LOG_FILE, "w") as f:
            json.dump(bot.trade_log, f, indent=2)

        # 5. Wait before next screen capture
        time.sleep(30)  # 30-second interval

except KeyboardInterrupt:
    print("Bot stopped manually. Saving state...")
    with open(LOG_FILE, "w") as f:
        json.dump(bot.trade_log, f, indent=2)
    print(f"Final Capital: ${bot.capital:.2f}")
