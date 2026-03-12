#!/usr/bin/env python3
import requests
import time
import subprocess

WALLET = "0x400ec5a2ff6afbd42d169a86ae0cac5dcd4db296"
GLM_API = f"https://api.polygonscan.com/api?module=account&action=tokenbalance&contractaddress=0x363c3a8cf4fd2da9c93ede8ac6739d962cf8ab2b&address={WALLET}&tag=latest&apikey=YourPolygonScanKey"  # Free key @ polygonscan.com

def check_glm():
    resp = requests.get(GLM_API).json()
    balance = int(resp['result']) / 10**18 if resp['result'] != '0' else 0
    print(f"💰 GLM BALANCE: {balance} → TX COUNT: Check polygonscan")
    if balance > 0:
        subprocess.run(['ollama', 'run', 'qwen2.5:7b', f"Earnings proof: {balance} GLM. Ramp providers?"])
    return balance

while True:
    check_glm()
    time.sleep(300)  # 5min
