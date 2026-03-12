from finance import calculate_roi

def test_calculate_roi_basic():
    # $10,000 at 2% monthly for 1 month
    result = calculate_roi(10000, 0.02, 1)
    assert round(result, 2) == 200.00
