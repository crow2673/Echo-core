import pyautogui
from PIL import Image
import pytesseract

class ScreenWatcher:
    def __init__(self, region=None):
        """
        region: tuple (x, y, width, height) to capture part of the screen.
                None -> full screen
        """
        self.region = region

    def capture_screen(self):
        screenshot = pyautogui.screenshot(region=self.region)
        return screenshot

    def read_text(self):
        image = self.capture_screen()
        text = pytesseract.image_to_string(image)
        return text

    def extract_numbers(self, text):
        """
        Extract floats from OCR text.
        """
        import re
        numbers = re.findall(r'\d+\.\d+|\d+', text)
        return [float(n) for n in numbers]
