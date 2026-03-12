#!/bin/bash
echo "Starting Dev / Content workspace..."

# 1) Open Dev.to dashboard (for writing/publishing)
if command -v google-chrome >/dev/null 2>&1; then
  google-chrome "https://dev.to/dashboard" >/dev/null 2>&1 &
elif command -v google-chrome-stable >/dev/null 2>&1; then
  google-chrome-stable "https://dev.to/dashboard" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "https://dev.to/dashboard" >/dev/null 2>&1 &
fi

# 2) Open LM Studio GUI
if command -v lmstudio >/dev/null 2>&1; then
  lmstudio >/dev/null 2>&1 &
fi

# 3) Open file manager in content_bot
if command -v nautilus >/dev/null 2>&1; then
  nautilus "$HOME/content_bot" >/dev/null 2>&1 &
fi

# 4) Open topics file in default editor
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$HOME/content_bot/topics.txt" >/dev/null 2>&1 &
fi

echo "Dev / Content workspace launched."
