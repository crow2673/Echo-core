import time
from micro_safe_trading_bot_live import MicroSafeTradingBotLive
from echo_trade_feed import generate_trades_from_echo

# Initialize bot with safe capital rules
bot = MicroSafeTradingBotLive(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Continuous loop to pull trades from Echo
while True:
    trade_feed = generate_trades_from_echo()  # Fetch trades from Echo
    for trade in trade_feed:
        principal, monthly_rate, months = trade
        approved = bot.evaluate_trade(principal, monthly_rate, months)
        expected_profit = bot.trade_log[-1]["expected_profit"]
        print(f"Trade {trade} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | Expected Profit: ${expected_profit:.2f}")
        print(f"Current Capital: ${bot.capital:.2f}\n")

    # Wait before fetching new trades (simulate new data from Echo)
    time.sleep(5)  # adjust timing as needed (seconds)
