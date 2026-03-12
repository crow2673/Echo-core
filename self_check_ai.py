#!/usr/bin/env python3
import subprocess
import shutil
import socket
from datetime import datetime

def cmd_ok(cmd, timeout=5):
    try:
        subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout)
        return True
    except Exception:
        return False

def tcp_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def main():
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"Echo AI Self-Check ({ts})")
    print("="*60)

    # Ollama presence
    ollama_path = shutil.which("ollama")
    print(f"ollama in PATH: {ollama_path if ollama_path else 'NO'}")

    # Ollama reachability: prefer CLI, fallback to TCP check
    ollama_cli_ok = cmd_ok(["ollama", "ps"], timeout=8) if ollama_path else False
    ollama_tcp_ok = tcp_open("127.0.0.1", 11434, timeout=1.0)

    print(f"ollama ps works: {ollama_cli_ok}")
    print(f"tcp 127.0.0.1:11434 open: {ollama_tcp_ok}")

    if ollama_cli_ok or ollama_tcp_ok:
        print("SERVICE OK: ollama")
    else:
        print("SERVICE DOWN: ollama (not reachable via CLI or TCP)")

    # Minimal system checks (AI-only)
    print("\nBasic checks:")
    print(f"tesseract present: {'YES' if shutil.which('tesseract') else 'NO'}")
    print(f"streamlit present: {'YES' if shutil.which('streamlit') else 'NO'}")

if __name__ == "__main__":
    main()
