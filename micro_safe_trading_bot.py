from finance import calculate_roi

class MicroSafeTradingBot:
    def __init__(self, starting_capital, reserve_fraction=0.5, profit_target_fraction=0.1, max_trade_fraction=0.2):
        """
        starting_capital: initial money you can spare
        reserve_fraction: fraction of capital to keep untouched
        profit_target_fraction: target profit as % of risked capital
        max_trade_fraction: maximum fraction of current capital to risk per trade
        """
        self.capital = starting_capital
        self.reserve_fraction = reserve_fraction
        self.profit_target_fraction = profit_target_fraction
        self.max_trade_fraction = max_trade_fraction
        self.trade_log = []

    def evaluate_trade(self, principal, monthly_rate, months):
        """
        Evaluate if a trade is safe and worth executing.
        Automatically scales principal if too high.
        Returns True if trade meets profit target.
        """
        available_capital = self.capital * (1 - self.reserve_fraction)
        # Cap the principal to the max_trade_fraction of available capital
        safe_principal = min(principal, available_capital * self.max_trade_fraction)
        if safe_principal <= 0:
            decision = False
            expected_profit = 0
        else:
            expected_profit = calculate_roi(safe_principal, monthly_rate, months)
            min_profit = safe_principal * self.profit_target_fraction
            decision = expected_profit >= min_profit

        # Log trade
        self.trade_log.append({
            "capital_before": self.capital,
            "principal": safe_principal,
            "monthly_rate": monthly_rate,
            "months": months,
            "expected_profit": expected_profit,
            "profit_target": min_profit if safe_principal>0 else 0,
            "approved": decision
        })

        # Update capital if approved
        if decision:
            self.capital += expected_profit

        return decision

    def get_trade_log(self):
        return self.trade_log

    def get_current_capital(self):
        return self.capital
