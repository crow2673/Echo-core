#!/usr/bin/env python3
"""
Hardened CLI loop for Echo chat.

Changes vs original:
- Handles Ctrl+C / Ctrl+D cleanly
- Limits input size (basic DoS protection)
- Stricter exception handling + optional debug mode
- Safe/consistent output formatting
- Avoids printing raw exception details unless DEBUG=1
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Optional

from echo_command import handle_command


PROMPT = "Andrew > "
BOT_PREFIX = "Echo > "
MAX_INPUT_CHARS = 4096  # adjust as needed


def _safe_print(line: str) -> None:
    # Avoid crashing on weird encodings / broken pipes
    try:
        print(line, flush=True)
    except (BrokenPipeError, OSError):
        # If output is piped and downstream closes early, exit cleanly.
        sys.exit(0)


def _format_response(resp: object) -> str:
    if resp is None:
        return "(acknowledged)"
    if isinstance(resp, str):
        return resp if resp.strip() else "(acknowledged)"
    # Never assume handle_command returns a string
    return str(resp)


def main() -> int:
    debug = os.getenv("DEBUG", "").strip() == "1"

    _safe_print("Echo chat online. Type 'exit' to quit.")

    while True:
        try:
            msg = input(PROMPT)
        except EOFError:
            _safe_print(f"\n{BOT_PREFIX}goodbye")
            return 0
        except KeyboardInterrupt:
            _safe_print(f"\n{BOT_PREFIX}interrupted (type 'exit' to quit)")
            continue

        msg = msg.strip()

        if not msg:
            # Ignore empty input (prevents accidental command handling)
            continue

        if len(msg) > MAX_INPUT_CHARS:
            _safe_print(f"{BOT_PREFIX}input too long (max {MAX_INPUT_CHARS} chars)")
            continue

        if msg.lower() in {"exit", "quit"}:
            _safe_print(f"{BOT_PREFIX}goodbye")
            return 0

        try:
            resp = handle_command(msg)
            _safe_print(f"{BOT_PREFIX}{_format_response(resp)}")
        except Exception as e:
            if debug:
                _safe_print(f"{BOT_PREFIX}error: {e!r}")
                traceback.print_exc()
            else:
                _safe_print(f"{BOT_PREFIX}error: something went wrong (set DEBUG=1 for details)")

    # unreachable
    # return 0


if __name__ == "__main__":
    raise SystemExit(main())
