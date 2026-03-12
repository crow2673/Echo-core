from PIL import ImageGrab
import time

try:
    print("Trying to capture full screen...")
    img = ImageGrab.grab()
    if img is None:
        print("Capture returned None")
    else:
        img.save("test_capture.png")
        print("Saved test_capture.png successfully")
except Exception as e:
    print("Error:", str(e))
