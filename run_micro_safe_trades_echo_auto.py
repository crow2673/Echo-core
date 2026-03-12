from micro_safe_trading_bot_echo import MicroSafeTradingBotEcho
from echo_ai_trade_feed import generate_echo_trades

# Initialize bot
bot = MicroSafeTradingBotEcho(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.0,
    watch_interval=5,
    platform_name="Robinhood",
    platform_rules=None
)

# Run the bot with live Echo AI feed
try:
    bot.run_echo_ai_feed(generate_echo_trades())
except KeyboardInterrupt:
    print("Bot stopped manually. Saving state...")
    print(f"Final Capital: ${bot.capital:.2f}")
