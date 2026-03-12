from safe_trading_bot import SafeTradingBot

def test_trade_approved():
    bot = SafeTradingBot(capital=10000, max_risk_per_trade=0.02)
    # Principal $200 is 2% of 10k, expected profit $4 at 2% monthly for 1 month
    assert bot.evaluate_trade(principal=200, monthly_rate=0.02, months=1, min_profit=3) is True

def test_trade_rejected_low_profit():
    bot = SafeTradingBot(capital=10000, max_risk_per_trade=0.02)
    # Principal $200, expected profit $2 < min_profit 3
    assert bot.evaluate_trade(principal=200, monthly_rate=0.01, months=1, min_profit=3) is False

def test_trade_rejected_exceeds_max_risk():
    bot = SafeTradingBot(capital=10000, max_risk_per_trade=0.02)
    # Principal $500 exceeds 2% max risk of capital
    decision = bot.evaluate_trade(principal=500, monthly_rate=0.02, months=1, min_profit=3)
    assert decision is True  # Allowed principal capped at $200
    last_trade = bot.get_trade_log()[-1]
    assert last_trade['principal'] == 200
