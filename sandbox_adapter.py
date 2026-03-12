from platform_adapter import PlatformAdapter

class SandboxAdapter(PlatformAdapter):
    """
    Simulated platform for testing trades safely.
    """

    def __init__(self):
        self.trade_history = []

    def get_trades(self):
        # Example: provide random or fixed trades
        # Format: (principal, monthly_rate, months, fee)
        trades = [
            (5, 0.05, 1, 0.2),
            (10, 0.03, 1, 0.2),
            (15, 0.02, 2, 0.2)
        ]
        return trades

    def execute_trade(self, trade):
        # Just log the trade; no real money
        self.trade_history.append(trade)
        return True  # always "success"
