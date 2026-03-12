import random

def generate_echo_trades():
    """
    Example generator simulating Echo AI trade suggestions.
    Each yield: (principal, monthly_rate, months, fee)
    """
    while True:
        principal = round(random.uniform(1, 20), 2)  # micro trade size
        rate = round(random.uniform(0.01, 0.07), 4)  # 1%–7% monthly
        months = random.randint(1, 3)
        fee = round(random.uniform(0.0, 0.2), 2)     # simulate platform fees
        yield (principal, rate, months, fee)
