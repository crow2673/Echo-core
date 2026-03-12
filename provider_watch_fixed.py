#!/usr/bin/env python3
import requests
import time
import subprocess
import re

WALLET = "0x400ec5a2ff6afbd42d169a86ae0cac5dcd4db296"
GLM_CONTRACT = "0x363c3a8cf4fd2da9c93ede8ac6739d962cf8ab2b"
APIKEY = "YourPolygonScanKeyHere"  # EDIT vim provider_watch_fixed.py → YOUR KEY

def check_glm():
    url = f"https://api.polygonscan.com/api?module=account&action=tokentx&address={WALLET}&startblock=0&endblock=99999999&sort=desc&apikey={APIKEY}"
    try:
        resp = requests.get(url).json()
        txs = len(resp['result']) if 'result' in resp else 0
        balance_url = f"https://api.polygonscan.com/api?module=account&action=tokenbalance&contractaddress={GLM_CONTRACT}&address={WALLET}&tag=latest&apikey={APIKEY}"
        bal_resp = requests.get(balance_url).json()
        balance = int(bal_resp['result']) / 1e18 if bal_resp['result'] != '0' else 0
        print(f"💰 GLM BAL: {balance} TXs: {txs} | Provider earnings ↑")
        if balance > 0 or txs > 0:
            subprocess.run(['ollama', 'run', 'qwen2.5:7b', f"GLM proof: bal{balance} tx{txs}. Node tasks accept?"])
    except:
        # NOKEY SCRAPE
        page = requests.get(f"https://polygonscan.com/address/{WALLET}#tokentxns").text
        tx_match = re.findall(r'<span class="hash-tag">.*?</span>', page)
        print(f"💰 GLM SCRAPE TXs: {len(tx_match)} | Check polygonscan manual")
    time.sleep(300)

while True:
    check_glm()
