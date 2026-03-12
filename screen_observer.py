import pytesseract
from PIL import Image
import re
import subprocess
import os
import time

class ScreenObserver:
    def __init__(self, region=None):
        self.region = region

    def capture_screen(self):
        temp_file = "/tmp/screen_observer_temp.png"
        print(f"[DEBUG] Attempting capture to {temp_file}")
        try:
            result = subprocess.run(
                ["gnome-screenshot", "-f", temp_file],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"[DEBUG] gnome-screenshot stdout: {result.stdout.strip()}")
            print(f"[DEBUG] gnome-screenshot stderr: {result.stderr.strip()}")
            if os.path.exists(temp_file):
                print(f"[DEBUG] File created, size: {os.path.getsize(temp_file)} bytes")
                img = Image.open(temp_file)
                print(f"[DEBUG] Image opened, size: {img.size}")
                os.remove(temp_file)
                print("[DEBUG] Temp file removed")
                return img
            else:
                raise RuntimeError("File not created after gnome-screenshot")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"gnome-screenshot failed (code {e.returncode}): {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Capture failed: {str(e)}")

    def extract_numbers(self, img):
        print("[DEBUG] Starting OCR...")
        try:
            text = pytesseract.image_to_string(img)
            print(f"[DEBUG] OCR raw text (first 300 chars):\n{text[:300]}")
            matches = re.findall(r'\$?(\d+\.\d+|\d+)', text.replace(',', ''))
            print(f"[DEBUG] Extracted numbers: {matches}")
            return [float(m) for m in matches]
        except Exception as e:
            print(f"[DEBUG] OCR failed: {str(e)}")
            return []

    def observe(self):
        print("[DEBUG] Starting observe cycle")
        img = self.capture_screen()
        numbers = self.extract_numbers(img)
        print(f"[DEBUG] Observe completed - numbers: {numbers}")
        return numbers


if __name__ == "__main__":
    observer = ScreenObserver()
    print("Starting screen observation test (gnome-screenshot)...")
    try:
        while True:
            nums = observer.observe()
            if nums:
                print("Detected numbers:", nums)
            else:
                print("No numbers detected this cycle")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Screen observation stopped manually.")
    except Exception as e:
        print("Error during observation:", str(e))
