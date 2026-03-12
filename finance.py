def calculate_roi(principal, monthly_rate, months):
    """
    Calculate simple ROI for given principal, monthly rate, and months.
    Returns expected profit.
    """
    return principal * ( (1 + monthly_rate) ** months - 1 )
