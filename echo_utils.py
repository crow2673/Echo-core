import sys

def safe_print(line: str) -> None:
    """Print safely, avoid crashing on broken pipes or encodings."""
    try:
        print(line, flush=True)
    except (BrokenPipeError, OSError):
        sys.exit(0)
