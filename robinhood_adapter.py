import robin_stocks.robinhood as r
import json
import os
from pathlib import Path
from platform_adapter import PlatformAdapter

class RobinhoodAdapter(PlatformAdapter):
    def __init__(self):
        self.config_path = Path("robinhood_config.json")
        self.logged_in = False

    def login(self):
        try:
            if not self.config_path.exists():
                print("Error: robinhood_config.json missing.")
                return False

            with open(self.config_path, "r") as f:
                config = json.load(f)

            print(f"[*] Attempting login for: {config['username']}")
            
            # Simplified login: The library will automatically prompt for 
            # the SMS/Email code if it is running in a terminal.
            login_data = r.login(
                username=config['username'], 
                password=config['password']
            )
            
            self.logged_in = True
            print("[+] Login Successful!")
            return True

        except Exception as e:
            print(f"[!] Login Exception: {e}")
            return False

    def get_balance(self):
        if not self.logged_in:
            if not self.login(): 
                return "0.00"
        
        try:
            # Get account profile data
            profile = r.load_account_profile()
            return profile.get('buying_power', '0.00')
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return "0.00"

    def get_trades(self):
        balance = self.get_balance()
        return [(float(balance), 0.00, 0, 0.0)]

if __name__ == "__main__":
    adapter = RobinhoodAdapter()
    balance = adapter.get_balance()
    print(f"\n--- Result ---\nCurrent Buying Power: ${balance}")
