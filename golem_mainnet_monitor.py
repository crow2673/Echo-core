import subprocess, time, json
while True:
    try:
        status = subprocess.check_output(['yagna', 'payment', 'status']).decode()
        offers = subprocess.check_output(['yagna', 'market', 'offers']).decode()[:500]
        print(f"[{time.ctime()}] Polygon GLM: {status}\nOffers: {offers}\n---")
    except: pass
    time.sleep(30)
