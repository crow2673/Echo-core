#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is required for the first local model backend."
  echo "Install Ollama, then run this installer again."
  exit 1
fi

ollama pull qwen2.5:7b

mkdir -p "$HOME/.self-evolving-ai/workspace"

echo
echo "Installed. Start with:"
echo "  $ROOT/run.sh"
