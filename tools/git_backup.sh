#!/bin/bash
cd ~/Echo
git add -A
git diff --cached --quiet && exit 0
git commit -m "Auto backup $(date +%Y-%m-%d\ %H:%M)"
git push origin main
