#!/usr/bin/env python3
import os, sys, subprocess
base = os.path.expanduser("~/Echo")
sys.exit(subprocess.call([os.path.join(base, "tools", "echo_status.py")] + sys.argv[1:]))
