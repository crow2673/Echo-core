from micro_safe_trading_bot_auto_screen import MicroSafeTradingBotAutoScreen

# Initialize with your capital, buffer, max risk, profit factor, and watch interval
bot = MicroSafeTradingBotAutoScreen(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.0,
    watch_interval=5
)

bot.run()
