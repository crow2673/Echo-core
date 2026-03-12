from micro_safe_trading_bot import MicroSafeTradingBot

class MicroSafeTradingBotLive(MicroSafeTradingBot):
    def __init__(self, capital, min_buffer=2.0, max_fraction=0.5, profit_factor=0.05, fee_per_trade=0.0):
        super().__init__(capital, min_buffer, max_fraction, profit_factor)
        self.fee_per_trade = fee_per_trade

    def run_platform_adapter(self, adapter):
        """
        adapter: instance of PlatformAdapter subclass
        Returns list of dicts with trade decisions
        """
        trades = adapter.get_trades()
        results = []
        for trade in trades:
            principal, monthly_rate, months, fee = trade
            self.fee_per_trade = fee
            approved = self.evaluate_trade(principal, monthly_rate, months)
            results.append({
                "trade": trade,
                "approved": approved
            })
        return results
