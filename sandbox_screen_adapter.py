from screen_watcher_adapter import ScreenWatcherAdapter

class SandboxScreenAdapter(ScreenWatcherAdapter):
    """
    Simulates a screen feed for testing.
    Returns predefined trade text as if OCR had read it.
    """

    def __init__(self, simulated_text=None, fee=0.2):
        super().__init__(region=None, fee=fee)
        # Example trades in OCR-like text
        self.simulated_text = simulated_text or """
        $5 @ 5% for 1 month
        $10 @ 3% for 1 month
        $15 @ 2% for 2 months
        """

    def get_trades(self):
        # Instead of real screen capture, parse simulated_text
        text = self.simulated_text
        import re
        trades = []
        pattern = r"\$([\d\.]+)\s*@\s*([\d\.]+)%\s*for\s*(\d+)\s*month"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            principal = float(m[0])
            monthly_rate = float(m[1])/100
            months = int(m[2])
            trades.append((principal, monthly_rate, months, self.fee))
        return trades
