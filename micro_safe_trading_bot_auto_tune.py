from micro_safe_trading_bot_live import MicroSafeTradingBotLive

class MicroSafeTradingBotAutoTune(MicroSafeTradingBotLive):
    def __init__(self, capital, min_buffer=2.0, max_fraction=0.5,
                 profit_factor=0.05, fee_per_trade=0.0,
                 max_profit_factor=0.10, min_profit_factor=0.01,
                 adjustment_step=0.005):
        """
        Auto-tuning bot based on trade performance.
        max_profit_factor / min_profit_factor: boundaries for dynamic profit factor
        adjustment_step: how much to increase/decrease profit factor per trade
        """
        super().__init__(capital, min_buffer, max_fraction, profit_factor, fee_per_trade)
        self.max_profit_factor = max_profit_factor
        self.min_profit_factor = min_profit_factor
        self.adjustment_step = adjustment_step

    def auto_tune_profit_factor(self, approved, expected_profit, trade_principal):
        """
        Adjusts profit_factor based on trade outcome.
        - If trade approved and profitable: increase profit_factor slightly
        - If trade rejected or small profit: decrease profit_factor slightly
        """
        if approved and expected_profit >= trade_principal * self.profit_factor:
            # can afford to be slightly more selective
            self.profit_factor = min(self.profit_factor + self.adjustment_step, self.max_profit_factor)
        else:
            # too strict? reduce to accept smaller wins
            self.profit_factor = max(self.profit_factor - self.adjustment_step, self.min_profit_factor)

    def evaluate_trade(self, principal, monthly_rate, months, dynamic_fee=None):
        """
        Evaluate trade and auto-tune profit factor afterward.
        """
        fee = dynamic_fee if dynamic_fee is not None else self.fee_per_trade
        available_capital = max(self.capital - self.min_buffer, 0)
        trade_principal = min(principal, available_capital * self.max_fraction, available_capital)

        if trade_principal <= 0:
            approved = False
            expected_profit = 0.0
        else:
            expected_profit = max(self.capital - self.min_buffer, 0)
            expected_profit = max(calculate_roi(trade_principal, monthly_rate, months) - fee, 0.0)
            approved = expected_profit >= trade_principal * self.profit_factor

        # Log trade
        self.trade_log.append({
            "capital_before": self.capital,
            "principal_used": trade_principal,
            "monthly_rate": monthly_rate,
            "months": months,
            "fee": fee,
            "expected_profit": expected_profit,
            "profit_target": trade_principal * self.profit_factor,
            "approved": approved,
            "current_profit_factor": self.profit_factor
        })

        if approved:
            self.capital += expected_profit

        # Auto-tune profit_factor
        self.auto_tune_profit_factor(approved, expected_profit, trade_principal)

        return approved
