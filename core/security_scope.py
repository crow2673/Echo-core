#!/usr/bin/env python3
"""
core/security_scope.py — the authorization gate for Echo's security tooling.

This is the safety core of the authorized security-testing toolkit (collab bus
#106/#108). Echo may ONLY recon/scan/test a target that is explicitly listed in
the scope file with a valid, unexpired authorization. Everything else is a hard
refuse. No wildcard default. Every decision is appended to an audit log.

The scope file is the authorization. Keep it under config/ (not memory/, which
Echo's autonomous loops can write) so she cannot grant herself new targets.
Hardening to come (Codex's lane): Ed25519-signed scope verified against a public
key in-repo, with the signing key held off-box; root-owned /etc/echo copy.

Usage as a library:
    from core.security_scope import ScopeGuard
    g = ScopeGuard()
    ok, reason, sid = g.authorize("192.168.1.171", caller="recon")
    g.require("8.8.8.8", caller="recon")   # raises PermissionError if not allowed

CLI:
    python3 -m core.security_scope check <target>
    python3 -m core.security_scope list
"""
import ipaddress
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCOPE_FILE = BASE / "config" / "security" / "authorized_scope.json"
AUDIT_LOG = BASE / "memory" / "security_scope_audit.jsonl"


class ScopeGuard:
    def __init__(self, scope_file: Path = SCOPE_FILE):
        self.scope_file = scope_file
        self.entries = self._load()

    def _load(self):
        if not self.scope_file.exists():
            return []
        try:
            data = json.loads(self.scope_file.read_text())
        except Exception:
            return []
        return data.get("scope", [])

    @staticmethod
    def _matches(target: str, entry_target: str) -> bool:
        """CIDR containment for IPs; exact (case-insensitive) match otherwise."""
        et = entry_target.strip()
        t = target.strip()
        if "/" in et:  # CIDR
            try:
                return ipaddress.ip_address(t) in ipaddress.ip_network(et, strict=False)
            except ValueError:
                return False
        # exact IP or hostname match
        try:
            return ipaddress.ip_address(t) == ipaddress.ip_address(et)
        except ValueError:
            return t.lower() == et.lower()

    def authorize(self, target: str, caller: str = "?"):
        """Return (allowed: bool, reason: str, scope_id: str|None). Always audits."""
        target = (target or "").strip()
        allowed, reason, sid = False, "no matching authorized scope (default deny)", None

        if not target:
            reason = "empty target"
        else:
            today = date.today().isoformat()
            for e in self.entries:
                et = e.get("target", "")
                if not et or not self._matches(target, et):
                    continue
                exp = e.get("expires_on", "")
                if exp and exp < today:
                    reason, sid = f"authorization expired {exp}", e.get("id")
                    allowed = False
                    break
                allowed, reason, sid = True, f"authorized: {e.get('authorization_type','?')} ({e.get('reference','')})", e.get("id")
                break

        self._audit(target, allowed, reason, sid, caller)
        return allowed, reason, sid

    def require(self, target: str, caller: str = "?"):
        allowed, reason, sid = self.authorize(target, caller)
        if not allowed:
            raise PermissionError(f"REFUSED {target}: {reason}")
        return sid

    def _audit(self, target, allowed, reason, sid, caller):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "target": target,
            "decision": "ALLOWED" if allowed else "REFUSED",
            "reason": reason,
            "scope_id": sid,
            "caller": caller,
        }
        try:
            AUDIT_LOG.parent.mkdir(exist_ok=True)
            with open(AUDIT_LOG, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    g = ScopeGuard()
    if args and args[0] == "list":
        print(f"Authorized scope ({SCOPE_FILE}):")
        for e in g.entries:
            print(f"  [{e.get('id')}] {e.get('target')} — {e.get('authorization_type')} "
                  f"(by {e.get('authorized_by')}, expires {e.get('expires_on')})")
    elif len(args) == 2 and args[0] == "check":
        ok, reason, sid = g.authorize(args[1], caller="cli")
        print(f"{'ALLOWED' if ok else 'REFUSED'} {args[1]} — {reason}" + (f" [{sid}]" if sid else ""))
        sys.exit(0 if ok else 1)
    else:
        print(__doc__.strip().split("\n\n")[0])
        print("\nUsage: python3 -m core.security_scope check <target> | list")


if __name__ == "__main__":
    main()
