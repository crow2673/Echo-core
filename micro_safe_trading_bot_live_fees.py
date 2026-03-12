from micro_safe_trading_bot_live import MicroSafeTradingBotLive

class MicroSafeTradingBotLiveFees(MicroSafeTradingBotLive):
    def __init__(self, capital, min_buffer=2.0, max_fraction=0.5, profit_factor=0.05, fee_per_trade=0.0):
        super().__init__(capital, min_buffer, max_fraction, profit_factor, fee_per_trade)

    def evaluate_trade_with_fee(self, principal, monthly_rate, months, fee=None):
        """
        fee: actual platform fee for this trade
        """
        if fee is None:
            fee = self.fee_per_trade
        available_capital = max(self.capital - self.min_buffer, 0)
        trade_principal = min(principal, available_capital * self.max_fraction, available_capital)
        if trade_principal <= 0:
            approved = False
            expected_profit = 0
        else:
            expected_profit = max(self.calculate_profit(trade_principal, monthly_rate, months) - fee, 0)
            approved = expected_profit >= trade_principal * self.profit_factor

        self.trade_log.append({
            "capital_before": self.capital,
            "principal_used": trade_principal,
            "monthly_rate": monthly_rate,
            "months": months,
            "expected_profit": expected_profit,
            "profit_target": trade_principal * self.profit_factor,
            "fee_applied": fee,
            "approved": approved
        })

        if approved:
            self.capital += expected_profit

        return approved
