import subprocess
import time
import ollama
from PIL import ImageEnhance, ImageFilter
import pytesseract
import os

def ocr_screen():
    os.environ['DISPLAY'] = ':0'
    result = subprocess.run(["scrot", "screen.png"])
    if os.path.exists('screen.png'):
        img = Image.open('screen.png').convert('L')
        img = ImageEnhance.Contrast(img).enhance(3)
        img = img.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, config='--psm 6 tesseract_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$% ')
        os.remove('screen.png')
        print(f"OCR len: {len(text)} Sample: {text[:100]}")
        return text or "DASH BLANK - BUY DIP"
    return "No screen"

while True:
    try:
        text = ocr_screen()
        resp = ollama.chat(model='qwen2.5:7b', messages=[{'role':'user', 'content': f"OCR Dash: {text}. Buy GLM dip?"}])
        print("qwen:", resp['message']['content'][:100])
        if 'buy' in resp['message']['content'].lower():
            subprocess.run(["/home/andrew/Echo/venv/bin/python3", "/home/andrew/Echo/echo_simple_agent.py"])
            print("🚀 OCR TRADE!")
    except Exception as e:
        print(f"OCR err: {e}")
    time.sleep(60)
