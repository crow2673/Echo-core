from micro_safe_trading_bot import MicroSafeTradingBot

# Example starting capital
capital = 20.0

# Initialize bot
bot = MicroSafeTradingBot(capital)

# Sample trades: (principal, monthly_rate, months)
trades = [
    (5, 0.05, 1),
    (10, 0.03, 1),
    (15, 0.02, 2),
    (8, 0.07, 1),
    (12, 0.01, 3)
]

print("Running MicroSafe Trading Bot...\n")

for trade in trades:
    principal, rate, months = trade
    approved = bot.evaluate_trade(principal, rate, months)
    print(f"Trade {trade} -> {'APPROVED ✅' if approved else 'REJECTED ❌'}")

print("\nTrade Log:")
for log in bot.get_trade_log():
    print(log)

print(f"\nCurrent Capital: ${bot.capital:.2f}")
