#!/usr/bin/env python3
import easyocr
import subprocess
import time
import re

reader = easyocr.Reader(['en'], gpu=True)  # RTX 3060 CUDA auto

def ocr_dash():
    # Scrot full dash (multi-tab: metrics/PS/logs)
    subprocess.run(['scrot', '-s', 'dash_scrot.png'])  # Select window
    time.sleep(1)
    results = reader.readtext('dash_scrot.png')
    text = ' '.join([res[1] for res in results])
    print(f"🟢 OCR DASH: {text[:500]}...")  # Len >0 now!
    
    # Parse keys: $0.2317 | Provider subs | Memory ramps
    price = re.search(r'\$[\d.]+', text)
    if price:
        print(f"📈 PRICE: {price.group()} → HOLD/STABLE")
        # Jarvis act on change
        subprocess.run(['ollama', 'run', 'qwen2.5:7b', f"Analyze dash: {text[:300]}. Trade?"])
    return len(text)

while True:
    len_text = ocr_dash()
    if len_text > 0:
        print("✅ OCR FIX: Text captured → TRADE TRIGGER LIVE")
        break
    time.sleep(10)
