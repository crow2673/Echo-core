from micro_safe_trading_bot_live_fees import MicroSafeTradingBotLiveFees
from screen_watcher_fees import ScreenWatcherFees
import time

bot = MicroSafeTradingBotLiveFees(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.0
)

watcher = ScreenWatcherFees()

def parse_trades_and_fees():
    text = watcher.read_text()
    numbers = watcher.extract_numbers(text)
    fees = watcher.extract_fees(text)
    
    trades = []
    for i in range(0, len(numbers), 3):
        if i+2 < len(numbers):
            fee = fees[i//3] if i//3 < len(fees) else 0.0
            trades.append((numbers[i], numbers[i+1], numbers[i+2], fee))
    return trades

print("Starting MicroSafe Trading Bot (screen input + fees)...")

try:
    while True:
        trade_feed = parse_trades_and_fees()
        for t in trade_feed:
            principal, rate, months, fee = t
            approved = bot.evaluate_trade_with_fee(principal, rate, months, fee)
            print(f"Trade {(principal, rate, months)} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | Fee: ${fee:.2f} | Capital: ${bot.capital:.2f}")
        time.sleep(5)
except KeyboardInterrupt:
    print("Bot stopped manually. Saving state...")
    print(f"Final Capital: ${bot.capital:.2f}")
