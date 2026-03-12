from safe_trading_bot import SafeTradingBot

# Initialize SafeTradingBot with your total capital
bot = SafeTradingBot(capital=10000, max_risk_per_trade=0.02)  # 2% risk per trade

# Example trades: (principal, monthly_rate, months, min_profit)
trades = [
    (5000, 0.02, 1, 50),
    (3000, 0.03, 1, 80),
    (7000, 0.015, 2, 200),
    (2000, 0.05, 1, 100)
]

# Evaluate trades
for trade in trades:
    principal, rate, months, min_profit = trade
    approved = bot.evaluate_trade(principal, rate, months, min_profit)
    status = "APPROVED ✅" if approved else "REJECTED ❌"
    print(f"Trade {trade} -> {status}")

# Optional: see full log
print("\nTrade Log:")
for log in bot.get_trade_log():
    print(log)
