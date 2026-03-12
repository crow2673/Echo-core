from finance import calculate_roi

class MicroSafeTradingBotFee:
    def __init__(self, capital, min_buffer=2.0, max_fraction=0.5, profit_factor=0.05, fee_per_trade=0.2):
        """
        capital: total money you can spare right now
        min_buffer: keep this amount safe, never risk it
        max_fraction: max fraction of available capital to risk in one trade
        profit_factor: expected profit fraction relative to principal to approve trade
        fee_per_trade: cost per trade (platform/trading fee)
        """
        self.capital = capital
        self.min_buffer = min_buffer
        self.max_fraction = max_fraction
        self.profit_factor = profit_factor
        self.fee_per_trade = fee_per_trade
        self.trade_log = []

    def evaluate_trade(self, principal, monthly_rate, months):
        """
        Decide whether a trade is safe, profitable, and worth executing after fees.
        """
        available_capital = max(self.capital - self.min_buffer, 0)
        trade_principal = min(principal, available_capital * self.max_fraction, available_capital)
        
        if trade_principal <= 0:
            approved = False
            expected_profit = 0
        else:
            expected_profit = calculate_roi(trade_principal, monthly_rate, months)
            net_profit = expected_profit - self.fee_per_trade
            approved = net_profit >= trade_principal * self.profit_factor

            if approved:
                self.capital += net_profit

        # Log the decision
        self.trade_log.append({
            "capital_before": self.capital,
            "principal_used": trade_principal,
            "monthly_rate": monthly_rate,
            "months": months,
            "expected_profit": expected_profit,
            "fee": self.fee_per_trade,
            "net_profit": expected_profit - self.fee_per_trade,
            "profit_target": trade_principal * self.profit_factor,
            "approved": approved
        })

        return approved

    def get_trade_log(self):
        return self.trade_log
