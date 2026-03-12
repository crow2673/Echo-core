from micro_safe_trading_bot_live import MicroSafeTradingBotLive
from screen_watcher_adapter import ScreenWatcherAdapter
import time

# ----------------------------
# CONFIGURATION
# ----------------------------
CAPITAL = 20.0        # Total money you can spare
MIN_BUFFER = 2.0      # Money never to risk
MAX_FRACTION = 0.5    # Max fraction of available capital per trade
PROFIT_FACTOR = 0.02  # Approve trade if expected profit >= 2% of trade
FEE_PER_TRADE = 0.1   # Fee per trade (adjust per platform)
SCREEN_REGION = (0, 0, 800, 600)  # x1, y1, x2, y2 for screen capture
SLEEP_INTERVAL = 30   # Seconds between screen scans

# ----------------------------
# INITIALIZE BOT AND ADAPTER
# ----------------------------
bot = MicroSafeTradingBotLive(
    capital=CAPITAL,
    min_buffer=MIN_BUFFER,
    max_fraction=MAX_FRACTION,
    profit_factor=PROFIT_FACTOR,
    fee_per_trade=FEE_PER_TRADE
)

adapter = ScreenWatcherAdapter(region=SCREEN_REGION, fee=FEE_PER_TRADE)

# ----------------------------
# HELPER FUNCTION: MOCK TRADE FEED
# ----------------------------
def mock_trade_feed():
    """
    Generates sample trades for testing without real platform
    """
    trades = [
        (2.0, 0.05, 1),
        (3.0, 0.03, 1),
        (4.0, 0.02, 2),
        (1.5, 0.06, 1)
    ]
    for t in trades:
        yield t

# ----------------------------
# RUN LOOP
# ----------------------------
print("Starting MicroSafe Trading Bot Full Auto...")

try:
    while True:
        # Choose either live screen watcher or mock trades
        # trades = adapter.get_trades()   # Uncomment for live screen
        trades = mock_trade_feed()        # Comment out if using live screen

        results = bot.run_echo_feed(trades)

        for r in results:
            t = r["trade"]
            print(f"Trade {t} -> {'APPROVED ✅' if r['approved'] else 'REJECTED ❌'} | "
                  f"Expected Profit: ${r.get('expected_profit',0):.2f} | "
                  f"Capital: ${bot.capital:.2f}")

        time.sleep(SLEEP_INTERVAL)

except KeyboardInterrupt:
    print("\nBot stopped manually. Saving state...")
    print(f"Final Capital: ${bot.capital:.2f}")

    # Optionally save trade log
    with open("micro_safe_trade_log.txt", "w") as f:
        for entry in bot.get_trade_log():
            f.write(str(entry) + "\n")
    print("Trade log saved to micro_safe_trade_log.txt")
