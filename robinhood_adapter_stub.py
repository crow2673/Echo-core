from platform_adapter import PlatformAdapter

class RobinhoodAdapterStub(PlatformAdapter):
    def get_trades(self):
        """
        Replace with actual API or screen capture logic.
        Returns trades: (principal, monthly_rate, months, fee)
        """
        # Example mock trades
        return [
            (5.0, 0.05, 1, 0.2),
            (10.0, 0.03, 1, 0.2),
            (2.0, 0.06, 1, 0.2)
        ]

    def execute_trade(self, trade):
        """
        Placeholder for real trade execution.
        """
        print(f"Executing trade: {trade}")
        return True
