from micro_safe_trading_bot_multi_platform import MicroSafeTradingBotMultiPlatform

# Example rules for platforms (can be extended for other brokers)
platform_rules = {
    "Robinhood": {
        "regex_trade": r'\d+\.\d+|\d+',
        "regex_fee": r'\d+\.\d+|\d+'
    },
    "OtherBroker": {
        "regex_trade": r'\d+\.\d+|\d+',
        "regex_fee": r'\d+\.\d+|\d+'
    }
}

bot = MicroSafeTradingBotMultiPlatform(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.0,
    watch_interval=5,
    platform_name="Robinhood",
    platform_rules=platform_rules
)

bot.run()
