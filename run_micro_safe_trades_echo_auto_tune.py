from micro_safe_trading_bot_auto_tune import MicroSafeTradingBotAutoTune

# Initialize bot with auto-tune
bot = MicroSafeTradingBotAutoTune(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Example Echo feed generator
def echo_trade_feed():
    trades = [
        (5, 0.05, 1),
        (10, 0.03, 1),
        (15, 0.02, 2),
        (8, 0.07, 1, 0.1),
        (12, 0.01, 3)
    ]
    for t in trades:
        yield t

# Run trades
results = bot.run_echo_feed(echo_trade_feed())

print("Running MicroSafe Trading Bot Auto-Tune...\n")
for r in results:
    t = r["trade"]
    approved = r["approved"]
    fee_info = t[3] if len(t) == 4 else bot.fee_per_trade
    pf = bot.profit_factor
    log_msg = (
        f"Trade {t[:3]} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | "
        f"Fee Applied: ${fee_info:.2f} | "
        f"Current Capital: ${bot.capital:.2f} | "
        f"Profit Factor Now: {pf:.3f}"
    )
    print(log_msg)

print("\nFinal Capital: ${:.2f}".format(bot.capital))
