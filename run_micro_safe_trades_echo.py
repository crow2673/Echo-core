from micro_safe_trading_bot_live import MicroSafeTradingBotLive

bot = MicroSafeTradingBotLive(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Placeholder: Echo trade feed
def echo_trade_feed():
    trades = [
        (5, 0.05, 1),
        (10, 0.03, 1),
        (15, 0.02, 2),
        (8, 0.07, 1),
        (12, 0.01, 3)
    ]
    for t in trades:
        yield t

results = bot.run_echo_feed(echo_trade_feed())

for r in results:
    t = r["trade"]
    print(f"Trade {t} -> {'APPROVED ✅' if r['approved'] else 'REJECTED ❌'} | Expected Profit: ${r['expected_profit']:.2f}")

print(f"\nCurrent Capital: ${bot.capital:.2f}")
