from micro_safe_trading_bot_live import MicroSafeTradingBotLive

# Initialize bot with $20 capital
bot = MicroSafeTradingBotLive(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Simulated sandbox trades
sandbox_trades = [
    (5, 0.05, 1),
    (10, 0.03, 1),
    (15, 0.02, 2),
    (3, 0.06, 1),
    (7, 0.025, 1)
]

print("Running Sandbox MicroSafe Trading Bot Test...")

for t in sandbox_trades:
    approved = bot.evaluate_trade(*t)
    print(f"Trade {t} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | Current Capital: ${bot.capital:.2f}")

print("\nTrade Log:")
for entry in bot.get_trade_log():
    print(entry)
