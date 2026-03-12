"""
echo_trade_feed.py
Provides a live or simulated feed of trade suggestions from Echo.
Each trade is a tuple: (principal, monthly_rate, months)
"""

import random
import time

# Optional: configure max trades per run
MAX_TRADES_PER_BATCH = 5

def generate_trades_from_echo():
    """
    Generator that yields trade suggestions.
    In a real scenario, this would pull from Echo's AI suggestions,
    API, or database.
    """

    # Example: simulate random micro-trades
    trade_batch = []
    for _ in range(MAX_TRADES_PER_BATCH):
        # Random principal between $1 and $20
        principal = round(random.uniform(1, 20), 2)
        # Random monthly_rate between 1% and 7%
        monthly_rate = round(random.uniform(0.01, 0.07), 4)
        # Random duration between 1-3 months
        months = random.randint(1, 3)
        trade_batch.append((principal, monthly_rate, months))

    # Yield trades one by one
    for trade in trade_batch:
        yield trade
        # Optional delay to simulate streaming from Echo
        time.sleep(0.1)

# Example usage for testing
if __name__ == "__main__":
    for t in generate_trades_from_echo():
        print(f"Suggested trade from Echo: {t}")
