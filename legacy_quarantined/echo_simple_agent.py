#!/usr/bin/env python3
import os
import subprocess
import json
import time
import ccxt
import psutil
import sys

os.chdir('/home/andrew/Echo')

print("🤖 Echo Ultimate: Trades + Autonomy + CCXT")

# KuCoin Exchange Setup (no sandbox mode)
exchange = ccxt.kucoin({
    'apiKey': os.getenv('KUCOIN_APIKEY', 'demo'),
    'secret': os.getenv('KUCOIN_SECRET', ''),
    'password': os.getenv('KUCOIN_PASSWORD', ''),
    'enableRateLimit': True,
})

if exchange.apiKey == 'demo' or not exchange.secret:
    print("⚠️ Warning: Using demo API key. Real trading is disabled.")
else:
    print("✅ Using real API keys for KuCoin.")

try:
    ollama = __import__('ollama')
except ImportError:
    print("⚠️ Ollama module not found. Please ensure ollama is installed in the virtual environment.")
    ollama = None

# Ollama interaction (if available)
if ollama:
    try:
        resp = ollama.chat(model='qwen2.5:7b', messages=[{'role': 'user', 'content': 'Autonomous GLM farm/trade ramp?'}])
        print("qwen:", resp['message']['content'][:150])
    except Exception as e:
        print(f"⚠️ Ollama chat error: {e}")
        print("Ollama fallback: Ramp")

# CCXT Trade Ramp
try:
    ticker = exchange.fetch_ticker('GLM/USDT')['last']
    print(f'GLM Live: {ticker}')
    if ticker < 0.045:
        print('🚀 SIM BUY 10 GLM (add keys for live trading)')
        order = {'id': 'sim', 'price': ticker}
    else:
        order = {'hold': ticker}
except Exception as e:
    print(f'CCXT error: {e}')
    order = {'error': str(e)}

# Run the trading bot (ramp mode)
subprocess.run(
    ['/home/andrew/Echo/venv/bin/python3', 'trading_bot.py', 'ramp']
)
print("GLM ramped | Offers live")

# Write the memory log
log = {'ts': time.time(), 'glml': ticker if 'ticker' in locals() else 0, 'order': order, 'action': 'ramp'}
with open('echo_memory.json', 'a') as f:
    f.write(json.dumps(log) + '\n')
print("✅ Memory | Dashboard | Provider = Earnings Farm")

# Jarvis Self-Improvement: Echo reviews memory and system metrics
if ollama:
    try:
        memory_lines = open('echo_memory.json').readlines()[-10:]
        cpu_load = psutil.cpu_percent(interval=1)
        mem_load = psutil.virtual_memory().percent
        self_resp = ollama.chat(model='qwen2.5:7b', messages=[
            {'role': 'system', 'content': 'You are Echo Jarvis. Review memory and system load. Suggest next ramp strategy.'},
            {'role': 'user', 'content': f"Memory ramp: {memory_lines}. Current GLM: {ticker}. CPU load: {cpu_load}%. Memory load: {mem_load}%. What next tweak?"}
        ])
        print("Jarvis Echo:", self_resp['message']['content'][:200])
    except Exception as e:
        print(f"⚠️ Ollama self-response error: {e}")

# Self-Check and AI Reasoning: Echo analyzes its own environment
try:
    result = subprocess.run(
        ['/home/andrew/Echo/venv/bin/python3', 'self_check.py'],
        capture_output=True, text=True
    )
    self_check_output = result.stdout
    print("Self-Check Output:\n", self_check_output)

    if ollama:
        diagnosis_resp = ollama.chat(model='qwen2.5:7b', messages=[
            {'role': 'system', 'content': 'You are Echo Jarvis. Analyze the system self-check and recommend next actions.'},
            {'role': 'user', 'content': f"Self-check output:\n{self_check_output}. What should we do next?"}
        ])
        print("Self-Diagnosis Suggestion:", diagnosis_resp['message']['content'][:300])

        # Optional: Auto-fix mode (set AUTO_FIX=True for automatic fixes)
        AUTO_FIX = False  # Change this to True if you want Echo to attempt auto-fixes
        if AUTO_FIX:
            if 'Missing Python packages' in self_check_output:
                missing_pkgs = [line.split(':')[1].strip() for line in self_check_output.splitlines() if 'Missing Python packages' in line]
                for pkg in missing_pkgs:
                    print(f"Auto-fixing: Installing package {pkg}")
                    subprocess.run(['/home/andrew/Echo/venv/bin/pip', 'install', pkg])
            
            if 'Some services are not running' in self_check_output:
                missing_services = [line.split(':')[1].strip() for line in self_check_output.splitlines() if 'Some services are not running' in line]
                for svc in missing_services:
                    print(f"Auto-fixing: Restarting service {svc}")
                    subprocess.run(['systemctl', '--user', 'restart', svc])
except Exception as e:
    print(f"⚠️ Self-check or diagnosis error: {e}")

# Handle interactive or daemon mode
DAEMON_MODE = '--daemon' in sys.argv

if __name__ == "__main__":
    if DAEMON_MODE:
        print("Running in daemon mode (no interactive input).")
        while True:
            user_cmd = os.getenv('CMD', 'hold 0.2302')  # Default command or from env
            time.sleep(60)
    else:
        print("Running in interactive mode.")
        while True:
            user_cmd = input("Jarvis: ").strip()
            try:
                if ollama:
                    jarvis_resp = ollama.chat(model='qwen2.5:7b', messages=[
                        {'role': 'system', 'content': 'You are Echo Jarvis. Act on command, ramp GLM.'},
                        {'role': 'user', 'content': f"Command: {user_cmd}. Memory: {open('echo_memory.json').read()[-1000:]}"}
                    ])
                    print("Jarvis: ", jarvis_resp['message']['content'])
                else:
                    print("Ollama not available. Command received:", user_cmd)
            except Exception as e:
                print(f"⚠️ Error processing command: {e}")
