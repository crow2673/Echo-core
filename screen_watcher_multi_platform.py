import pytesseract
from PIL import ImageGrab
import re

class ScreenWatcherMulti:
    def __init__(self, platform_rules=None):
        """
        platform_rules: dict containing platform-specific parsing rules
        e.g., {"Robinhood": {"regex_trade": ..., "regex_fee": ...}, ...}
        """
        self.platform_rules = platform_rules or {}

    def read_text(self):
        # Capture screen and OCR
        img = ImageGrab.grab()
        text = pytesseract.image_to_string(img)
        return text

    def parse_trades_and_fees(self, platform_name="default"):
        text = self.read_text()
        rules = self.platform_rules.get(platform_name, {})
        trade_pattern = rules.get("regex_trade", r'\d+\.\d+|\d+')
        fee_pattern = rules.get("regex_fee", r'\d+\.\d+|\d+')
        
        numbers = [float(n) for n in re.findall(trade_pattern, text)]
        fees = [float(f) for f in re.findall(fee_pattern, text)]
        
        trades = []
        for i in range(0, len(numbers), 3):
            if i+2 < len(numbers):
                fee = fees[i//3] if i//3 < len(fees) else 0.0
                trades.append((numbers[i], numbers[i+1], numbers[i+2], fee))
        return trades
