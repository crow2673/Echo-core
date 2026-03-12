from micro_safe_trading_bot_fee import MicroSafeTradingBotFee

# Example starting capital
capital = 20.0

# Instantiate bot
bot = MicroSafeTradingBotFee(capital, min_buffer=2.0, max_fraction=0.5, profit_factor=0.05, fee_per_trade=0.2)

# Example trade suggestions: (principal, monthly_rate, months)
trades = [
    (5, 0.05, 1),
    (10, 0.03, 1),
    (15, 0.02, 2),
    (8, 0.07, 1),
    (12, 0.01, 3)
]

print("Running MicroSafe Trading Bot with Fees...\n")

for t in trades:
    principal, rate, months = t
    approved = bot.evaluate_trade(principal, rate, months)
    status = "APPROVED ✅" if approved else "REJECTED ❌"
    print(f"Trade {t} -> {status}")

print("\nTrade Log:")
for entry in bot.get_trade_log():
    print(entry)

print(f"\nCurrent Capital: ${bot.capital:.2f}")
