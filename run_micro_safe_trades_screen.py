from micro_safe_trading_bot_live import MicroSafeTradingBotLive
from screen_watcher_adapter import ScreenWatcherAdapter
import time

# Initialize bot
bot = MicroSafeTradingBotLive(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05
)

# Define screen region (adjust to your platform)
region = (0, 0, 800, 600)  # x1, y1, x2, y2
adapter = ScreenWatcherAdapter(region=region, fee=0.2)

print("Starting Screen-Watched MicroSafe Trading Bot...")
try:
    while True:
        trades = adapter.get_trades()
        results = bot.run_platform_adapter(adapter)

        for r in results:
            t = r["trade"]
            print(f"Trade {t} -> {'APPROVED ✅' if r['approved'] else 'REJECTED ❌'} | Current Capital: ${bot.capital:.2f}")
        
        time.sleep(10)  # Check every 10 seconds
except KeyboardInterrupt:
    print("Bot stopped manually. Saving state...")
    print(f"Final Capital: ${bot.capital:.2f}")
