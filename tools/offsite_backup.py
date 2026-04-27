#!/usr/bin/env python3
"""
tools/offsite_backup.py — Encrypted offsite backup of Echo's soul documents.
Runs at 3:00am daily via echo-offsite-backup.timer.
Compresses key files, encrypts with gpg symmetric, emails to Gmail.
"""
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/offsite_backup.log"

BACKUP_FILES = [
    "echo_contract.json",
    "memory/known_gaps.md",
    "memory/world_context.md",
    "memory/income_knowledge.md",
    "memory/standing_tasks.json",
    "memory/session_summary.json",
    "memory/content_strategy.json",
    "CHANGELOG.md",
    "registry.json",
]

LAST_BACKUP_FILE = BASE / "memory/offsite_backup_last.txt"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_env():
    env_file = Path.home() / ".config/echo/golem.env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def run():
    log("Offsite backup starting")
    env = load_env()

    gmail_user = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER") or os.environ.get("GMAIL_ADDRESS", "")
    gmail_app_password = env.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD", "")
    backup_email = env.get("BACKUP_EMAIL") or env.get("GMAIL_ADDRESS") or gmail_user
    gpg_passphrase = env.get("BACKUP_PASSPHRASE") or os.environ.get("BACKUP_PASSPHRASE", "")
    if not gpg_passphrase:
        log("ERROR: BACKUP_PASSPHRASE not set in golem.env — refusing to encrypt with default")
        sys.exit(1)

    if not gmail_user or not gmail_app_password:
        log("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in golem.env")
        sys.exit(1)

    # Build archive
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    archive_name = f"echo_backup_{stamp}.tar.gz"

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / archive_name
        enc_path = Path(tmpdir) / f"{archive_name}.gpg"

        # Create tar
        with tarfile.open(archive_path, "w:gz") as tar:
            added = 0
            for rel_path in BACKUP_FILES:
                full = BASE / rel_path
                if full.exists():
                    tar.add(full, arcname=rel_path)
                    added += 1
                    log(f"  + {rel_path}")
                else:
                    log(f"  - {rel_path} (missing, skipped)")

        log(f"Archive created: {archive_name} ({archive_path.stat().st_size} bytes, {added} files)")

        # Encrypt
        result = subprocess.run(
            ["gpg", "--batch", "--yes", "--passphrase", gpg_passphrase,
             "--symmetric", "--cipher-algo", "AES256",
             "-o", str(enc_path), str(archive_path)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            log(f"GPG encryption failed: {result.stderr}")
            sys.exit(1)
        log(f"Encrypted: {enc_path.stat().st_size} bytes")

        # Send via Gmail SMTP
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email.mime.text import MIMEText
        from email import encoders

        msg = MIMEMultipart()
        msg["From"] = gmail_user
        msg["To"] = backup_email
        msg["Subject"] = f"Echo Backup {stamp}"
        msg.attach(MIMEText(
            f"Echo automated backup — {stamp}\n"
            f"Files: {added}\n"
            f"Encrypted with AES256 GPG.\n"
            f"Passphrase stored in golem.env as BACKUP_PASSPHRASE.\n",
            "plain"
        ))

        with open(enc_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={enc_path.name}")
        msg.attach(part)

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_app_password)
                server.sendmail(gmail_user, backup_email, msg.as_string())
            log(f"Backup emailed to {backup_email}")
        except Exception as e:
            log(f"Email send failed: {e}")
            sys.exit(1)

    LAST_BACKUP_FILE.write_text(datetime.now().isoformat())
    log("Offsite backup complete")

    try:
        from core.event_ledger import log_event
        log_event("system", "offsite_backup", f"backup emailed: {added} files", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
