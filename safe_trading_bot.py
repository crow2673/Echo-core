from finance import calculate_roi

class SafeTradingBot:
    def __init__(self, capital, max_risk_per_trade=0.02):
        """
        capital: total money you want to protect
        max_risk_per_trade: fraction of capital to risk in a single trade
        """
        self.capital = capital
        self.max_risk_per_trade = max_risk_per_trade
        self.trade_log = []

    def evaluate_trade(self, principal, monthly_rate, months, min_profit):
        """
        Decide whether a trade is safe and worth executing.
        """
        # Cap principal at max allowed risk
        safe_principal = min(principal, self.capital * self.max_risk_per_trade)
        profit = calculate_roi(safe_principal, monthly_rate, months)
        decision = profit >= min_profit
        # Log decision
        self.trade_log.append({
            "principal": safe_principal,
            "monthly_rate": monthly_rate,
            "months": months,
            "expected_profit": profit,
            "min_profit": min_profit,
            "approved": decision
        })
        return decision

    def get_trade_log(self):
        return self.trade_log
