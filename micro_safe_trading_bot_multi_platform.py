from micro_safe_trading_bot_live_fees import MicroSafeTradingBotLiveFees
from screen_watcher_multi_platform import ScreenWatcherMulti
import time

class MicroSafeTradingBotMultiPlatform(MicroSafeTradingBotLiveFees):
    def __init__(self, capital, min_buffer=2.0, max_fraction=0.5, profit_factor=0.05, fee_per_trade=0.0, watch_interval=5, platform_name="default", platform_rules=None):
        super().__init__(capital, min_buffer, max_fraction, profit_factor, fee_per_trade)
        self.watcher = ScreenWatcherMulti(platform_rules)
        self.watch_interval = watch_interval
        self.platform_name = platform_name

    def run(self):
        print(f"Starting MicroSafe Trading Bot Auto for platform: {self.platform_name}")
        try:
            while True:
                trade_feed = self.watcher.parse_trades_and_fees(self.platform_name)
                for t in trade_feed:
                    principal, rate, months, fee = t
                    approved = self.evaluate_trade_with_fee(principal, rate, months, fee)
                    print(f"Trade {(principal, rate, months)} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | Fee: ${fee:.2f} | Capital: ${self.capital:.2f}")
                time.sleep(self.watch_interval)
        except KeyboardInterrupt:
            print("Bot stopped manually. Saving state...")
            print(f"Final Capital: ${self.capital:.2f}")
