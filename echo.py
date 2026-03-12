#!/usr/bin/env python3
import os, sys, runpy

BASE = os.path.dirname(__file__)
os.chdir(BASE)

# Prefer canonical code in ./app
sys.path.insert(0, os.path.join(BASE, "app"))

runpy.run_path(os.path.join(BASE, "app", "echo_chat_main.py"), run_name="__main__")
