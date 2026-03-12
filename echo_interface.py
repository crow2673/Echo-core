class EchoDummy:
    def __init__(self, trades=None):
        self.trades = trades or []

    def get_trades(self):
        # Simulate live trade feed
        for t in self.trades:
            yield t
