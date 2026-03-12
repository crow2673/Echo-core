class PlatformAdapter:
    """
    Generic interface for any trading platform.
    Subclasses implement get_trades() and optionally execute_trade().
    """
    def get_trades(self):
        """
        Return a list or generator of trades:
        Each trade: (principal, monthly_rate, months, fee)
        """
        raise NotImplementedError

    def execute_trade(self, trade):
        """
        Execute a trade on the platform.
        Return True if successful.
        """
        raise NotImplementedError
