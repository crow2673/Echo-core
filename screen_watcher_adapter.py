from platform_adapter import PlatformAdapter
import pyscreenshot as ImageGrab
import pytesseract
import re

class ScreenWatcherAdapter(PlatformAdapter):
    """
    Watch a screen region and extract trades dynamically.
    Returns trades as: (principal, monthly_rate, months, fee)
    """
    def __init__(self, region=None, fee=0.2):
        """
        region: tuple (x1, y1, x2, y2) defining screen capture box
        fee: per trade fee
        """
        self.region = region
        self.fee = fee

    def get_trades(self):
        # Capture the screen region
        img = ImageGrab.grab(bbox=self.region)
        text = pytesseract.image_to_string(img)

        trades = []
        # Example regex pattern: "$10 @ 2% for 1 month"
        # You can adjust this based on the platform text
        pattern = r"\$([\d\.]+)\s*@\s*([\d\.]+)%\s*for\s*(\d+)\s*month"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            principal = float(m[0])
            monthly_rate = float(m[1])/100
            months = int(m[2])
            trades.append((principal, monthly_rate, months, self.fee))
        return trades
