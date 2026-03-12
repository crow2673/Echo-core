import robin_stocks.robinhood as r
import subprocess
import time
import sys
from robinhood_adapter import RobinhoodAdapter

def check_price(ticker, target_price):
    adapter = RobinhoodAdapter()
    adapter.login()
    
    print(f"[*] Monitoring {ticker}... Target: ${target_price}")
    
    while True:
        try:
            price = float(r.get_latest_price(ticker)[0])
            print(f"Current {ticker} price: ${price}")
            
            if price <= target_price:
                msg = f"ALERT: {ticker} has dropped to ${price}! Buying opportunity?"
                subprocess.run(["notify-send", "Echo Finance Alert", msg])
                print(f"[!] {msg}")
                break # Stop after alerting
                
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(30) # Check every 30 seconds

if __name__ == "__main__":
    # Example: Check if NVIDIA (NVDA) drops below $120
    # Usage: python3 echo_price_sentry.py TICKER TARGET_PRICE
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    target = float(sys.argv[2]) if len(sys.argv) > 2 else 120.00
    check_price(ticker, target)
