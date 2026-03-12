from micro_safe_trading_bot_live import MicroSafeTradingBotLive

class MicroSafeTradingBotPlatform(MicroSafeTradingBotLive):
    def run_platform_adapter(self, adapter):
        """
        Accepts a PlatformAdapter and evaluates all trades it provides.
        """
        trades = adapter.get_trades()
        results = []

        for trade in trades:
            principal, monthly_rate, months, fee = trade
            self.fee_per_trade = fee  # Update fee dynamically
            approved = self.evaluate_trade(principal, monthly_rate, months)
            if approved and hasattr(adapter, "execute_trade"):
                adapter.execute_trade(trade)
            results.append({"trade": trade, "approved": approved})
        return results
