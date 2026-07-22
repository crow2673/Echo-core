#!/usr/bin/env python3
"""
tools/tv_announce.py — Echo speaks an announcement through the living-room Roku TV.

Roku has no native TTS or text overlay, so the path is:
  1. synthesize speech locally (espeak-ng -> wav -> mp3 via ffmpeg)
  2. serve the mp3 from this machine over a short-lived local HTTP server
  3. tell the Roku (ECP "Play on Roku") to play that URL through the TV speakers

REQUIREMENT: the Roku's "Control by mobile apps -> Network access" must be
"Permissive" (not Limited/Default), or ECP launch/play returns
"ECP command not allowed in Limited mode."

Usage:
  python3 tools/tv_announce.py "Kids, come to the living room — Dad's calling"
  python3 tools/tv_announce.py --roku 192.168.1.171 --voice en-us "<message>"
"""
import argparse
import http.server
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ROKU = "192.168.1.171"
ROKU_MEDIA_PLAYER = "2213"  # Roku Media Player channel (Play on Roku target)


def _local_ip(target_ip: str) -> str:
    """The address on THIS host that the Roku can reach us at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 80))
        return s.getsockname()[0]
    finally:
        s.close()


def synth(text: str, out_mp3: Path, voice: str = "en-us") -> Path:
    """espeak-ng -> wav -> mp3. Returns the mp3 path."""
    wav = out_mp3.with_suffix(".wav")
    subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(wav), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
         "-b:a", "128k", str(out_mp3)],
        check=True,
    )
    wav.unlink(missing_ok=True)
    return out_mp3


def _serve(directory: Path, ip: str) -> tuple[http.server.HTTPServer, int]:
    """Start a background one-directory HTTP server; return (server, port)."""
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)
    httpd = http.server.HTTPServer((ip, 0), handler)  # port 0 -> ephemeral
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _ecp(roku: str, path: str, method: str = "POST") -> tuple[int, str]:
    req = urllib.request.Request(f"http://{roku}:8060/{path}", method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode(errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")
    except Exception as e:
        return 0, str(e)


def announce(text: str, roku: str = DEFAULT_ROKU, voice: str = "en-us",
             hold: float = 12.0) -> dict:
    """Synthesize `text` and play it on the Roku. Returns a result dict."""
    # Pre-flight: confirm ECP is actually permitted (Limited mode blocks playback).
    code, body = _ecp(roku, "query/apps", method="GET")
    if "not allowed in limited mode" in body.lower():
        return {"ok": False, "stage": "preflight",
                "error": "Roku is in Limited mode — set Control by mobile apps → "
                         "Network access → Permissive."}

    workdir = Path("/tmp/echo_tv_announce")
    workdir.mkdir(exist_ok=True)
    mp3 = synth(text, workdir / "announce.mp3", voice=voice)

    ip = _local_ip(roku)
    httpd, port = _serve(workdir, ip)
    url = f"http://{ip}:{port}/{mp3.name}"

    # Play on Roku: launch the Media Player with audio content metadata.
    params = urllib.parse.urlencode({
        "t": "a", "u": url, "songName": "Echo announcement",
        "artistName": "Echo", "albumName": "Home",
    })
    status, resp = _ecp(roku, f"launch/{ROKU_MEDIA_PLAYER}?{params}")
    result = {"ok": status in (200, 202), "stage": "play", "http": status,
              "url": url, "text": text, "resp": resp[:200]}

    time.sleep(hold)  # keep serving while it plays
    httpd.shutdown()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", help="what Echo should say on the TV")
    ap.add_argument("--roku", default=DEFAULT_ROKU)
    ap.add_argument("--voice", default="en-us")
    ap.add_argument("--hold", type=float, default=12.0)
    a = ap.parse_args()
    res = announce(a.text, roku=a.roku, voice=a.voice, hold=a.hold)
    print(res)
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
