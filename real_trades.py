#!/usr/bin/env python3
import subprocess
print("🚀 Golem Live: " + subprocess.run(["yagna", "payment", "status", "--network", "polygon"], capture_output=True, text=True).stdout)
print("Offers cycling → First task = GLM!")
