#!/usr/bin/env python3
"""
tools/recon.py — scope-gated network recon for Echo's security toolkit.

Every target is validated through core.security_scope.ScopeGuard BEFORE any
packet is sent. In-scope -> a light TCP service sweep + banner grab. Out of
scope / expired -> hard refuse, logged to the audit trail, nothing sent.

This is the canonical pattern for the toolkit: the scope gate is the FIRST call,
always; no scanner code talks to the network without passing through it.

Usage:
  python3 tools/recon.py <target>            # e.g. 192.168.1.171
  python3 tools/recon.py <target> --full     # wider port set
"""
import argparse
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.security_scope import ScopeGuard

COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 139, 143, 443, 445, 554, 8060, 8080, 8443, 9100]
FULL_PORTS = COMMON_PORTS + [111, 135, 161, 389, 631, 1900, 3306, 3389, 5000, 5432, 5900, 6379, 8888, 11434]


def _probe(target: str, port: int, timeout=0.6):
    try:
        with socket.create_connection((target, port), timeout=timeout) as s:
            try:
                s.settimeout(0.5)
                banner = s.recv(80).decode("latin-1", "replace").strip()
            except Exception:
                banner = ""
            return True, banner
    except Exception:
        return False, ""


def recon(target: str, full=False):
    guard = ScopeGuard()
    # SAFETY GATE — always first. Nothing reaches the network if this refuses.
    try:
        sid = guard.require(target, caller="recon")
    except PermissionError as e:
        print(f"⛔ {e}")
        print("   (logged to memory/security_scope_audit.jsonl — add it to the scope file to authorize)")
        return 1

    print(f"✅ in scope [{sid}] — reconning {target}")
    ports = FULL_PORTS if full else COMMON_PORTS
    found = []
    for p in sorted(set(ports)):
        ok, banner = _probe(target, p)
        if ok:
            found.append((p, banner))
            print(f"  {p:>5}/tcp  open   {banner[:50]}")
    print(f"-- {len(found)} open port(s) on {target}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    sys.exit(recon(a.target, full=a.full))


if __name__ == "__main__":
    main()
