#!/usr/bin/env python3
import robin_stocks.robinhood as r
import subprocess
import time
from robinhood_adapter import RobinhoodAdapter

ASSETS = ['FLOKI', 'SHIB', 'SOL', 'MEW']
PERCENT_THRESHOLD = 5.0 

def get_prices():
    prices = {}
    for ticker in ASSETS:
        try:
            data = r.crypto.get_crypto_quote(ticker)
            prices[ticker] = float(data['mark_price'])
        except: pass
    return prices

def monitor():
    adapter = RobinhoodAdapter()
    if not adapter.login(): return
    
    print(f"[*] Echo Volatility Monitor active for: {', '.join(ASSETS)}")
    initial_prices = get_prices()
    
    while True:
        time.sleep(60) 
        current_prices = get_prices()
        
        for ticker, price in current_prices.items():
            old_price = initial_prices.get(ticker)
            if not old_price: continue
            
            change = ((price - old_price) / old_price) * 100
            
            if abs(change) >= PERCENT_THRESHOLD:
                direction = "🚀 UP" if change > 0 else "📉 DOWN"
                msg = f"{ticker} is {direction} {change:.2f}% (Price: ${price:.8f})"
                print(f"[!] {msg}")
                subprocess.run(["notify-send", "Echo Crypto Alert", msg])
                initial_prices[ticker] = price

if __name__ == "__main__":
    monitor()
