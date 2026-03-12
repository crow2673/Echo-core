from trading_bot import should_execute_trade

def test_trade_approved():
    assert should_execute_trade(10000, 0.02, 1, 150) is True

def test_trade_rejected():
    assert should_execute_trade(10000, 0.01, 1, 150) is False
