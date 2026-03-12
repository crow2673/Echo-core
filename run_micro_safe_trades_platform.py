from micro_safe_trading_bot_platform import MicroSafeTradingBotPlatform
from robinhood_adapter_stub import RobinhoodAdapterStub
import time

bot = MicroSafeTradingBotPlatform(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.02,
    fee_per_trade=0.2
)

adapter = RobinhoodAdapterStub()

print("Starting Platform-Connected MicroSafe Bot...")
try:
    while True:
        results = bot.run_platform_adapter(adapter)
        for r in results:
            t = r["trade"]
            print(f"Trade {t} -> {'APPROVED ✅' if r['approved'] else 'REJECTED ❌'} | Capital: ${bot.capital:.2f}")
        time.sleep(30)
except KeyboardInterrupt:
    print("Bot stopped manually.")
    print(f"Final Capital: ${bot.capital:.2f}")
