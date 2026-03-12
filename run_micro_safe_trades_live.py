from micro_safe_trading_bot_live import MicroSafeTradingBotLive

# Starting capital — change as your available amount
capital = 20.0  

# Initialize bot with safe defaults
bot = MicroSafeTradingBotLive(
    capital=capital,
    min_buffer=2.0,       # always keep $2 safe
    max_fraction=0.5,     # risk max 50% of available capital per trade
    profit_factor=0.05,   # need 5% profit target per trade
    fee_per_trade=0.2     # platform/trading fee per trade
)

# Example trade suggestions from Echo or manually
trade_suggestions = [
    (5, 0.05, 1),
    (10, 0.03, 1),
    (15, 0.02, 2),
    (8, 0.07, 1),
    (12, 0.01, 3)
]

print("Running MicroSafe Trading Bot Live...\n")

# Evaluate all trades
results = bot.run_live_trades(trade_suggestions)

for r in results:
    t = r["trade"]
    status = "APPROVED ✅" if r["approved"] else "REJECTED ❌"
    print(f"Trade {t} -> {status}")

print("\nTrade Log:")
for entry in bot.get_trade_log():
    print(entry)

print(f"\nCurrent Capital: ${bot.capital:.2f}")
