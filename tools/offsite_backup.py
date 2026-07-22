#!/usr/bin/env python3
"""
tools/offsite_backup.py - encrypted offsite backup of Echo's key documents.

Local archive creation and encryption are separate from offsite delivery. A
transient SMTP failure preserves the encrypted artifact for bounded retry
instead of turning a completed local backup into a total backup failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import smtplib
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LOG = BASE / "logs/offsite_backup.log"
STATUS_PATH = BASE / "memory/offsite_backup_status.json"
LAST_BACKUP_FILE = BASE / "memory/offsite_backup_last.txt"
SPOOL_DIR = BASE / "memory/offsite_backups"
PENDING_DIR = SPOOL_DIR / "pending"
SENT_DIR = SPOOL_DIR / "sent"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_TIMEOUT_SECONDS = 30
MAX_DELIVERY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (60, 300, 900)

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


class BackupStageError(Exception):
    """Local archive/encryption stage failed."""


class DeliveryError(Exception):
    """Offsite transport failed after encrypted artifact was preserved."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def load_env() -> dict[str, str]:
    env_file = Path.home() / ".config/echo/golem.env"
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def load_status(path: Path = STATUS_PATH) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.rename(path)


def artifact_exists(status: dict[str, Any]) -> bool:
    artifact = status.get("artifact_path")
    return bool(artifact and (BASE / artifact).exists())


def pending_status_is_reusable(status: dict[str, Any]) -> bool:
    return (
        status.get("offsite_delivery_pending") is True
        and status.get("offsite_delivery_succeeded") is not True
        and artifact_exists(status)
    )


def due_for_retry(status: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or utcnow()
    next_retry = parse_time(status.get("next_retry_at"))
    return next_retry is None or now >= next_retry


def relative(path: Path) -> str:
    return str(path.relative_to(BASE))


def base_status(stamp: str) -> dict[str, Any]:
    return {
        "updated_at": iso_now(),
        "stamp": stamp,
        "local_backup_created": False,
        "encryption_completed": False,
        "offsite_delivery_pending": False,
        "offsite_delivery_succeeded": False,
        "offsite_delivery_failed": False,
        "delivery_attempts": 0,
        "max_delivery_attempts": MAX_DELIVERY_ATTEMPTS,
        "last_attempt_at": None,
        "next_retry_at": None,
        "last_error": None,
        "artifact_path": None,
        "archive_name": f"echo_backup_{stamp}.tar.gz",
        "stage": "starting",
    }


def record_status(status: dict[str, Any], **updates: Any) -> dict[str, Any]:
    status.update(updates)
    status["updated_at"] = iso_now()
    write_json_atomic(STATUS_PATH, status)
    return status


def create_archive(stamp: str, tmpdir: Path) -> tuple[Path, int]:
    archive_name = f"echo_backup_{stamp}.tar.gz"
    archive_path = tmpdir / archive_name
    added = 0
    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for rel_path in BACKUP_FILES:
                full = BASE / rel_path
                if full.exists():
                    tar.add(full, arcname=rel_path)
                    added += 1
                    log(f"  + {rel_path}")
                else:
                    log(f"  - {rel_path} (missing, skipped)")
    except Exception as exc:
        raise BackupStageError(f"archive creation failed: {exc}") from exc
    if not archive_path.exists() or archive_path.stat().st_size <= 0:
        raise BackupStageError("archive creation failed: archive missing or empty")
    log(f"Archive created: {archive_name} ({archive_path.stat().st_size} bytes, {added} files)")
    return archive_path, added


def encrypt_archive(archive_path: Path, passphrase: str, pending_dir: Path = PENDING_DIR) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    enc_path = pending_dir / f"{archive_path.name}.gpg"
    tmp_enc = enc_path.with_name(f"{enc_path.name}.{os.getpid()}.tmp")
    result = subprocess.run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--passphrase",
            passphrase,
            "--symmetric",
            "--cipher-algo",
            "AES256",
            "-o",
            str(tmp_enc),
            str(archive_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        try:
            tmp_enc.unlink()
        except FileNotFoundError:
            pass
        raise BackupStageError(f"GPG encryption failed: {result.stderr.strip()}")
    tmp_enc.rename(enc_path)
    log(f"Encrypted: {enc_path.stat().st_size} bytes")
    return enc_path


def compose_message(
    gmail_user: str,
    backup_email: str,
    stamp: str,
    added: int,
    enc_path: Path,
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = backup_email
    msg["Subject"] = f"Echo Backup {stamp}"
    msg.attach(
        MIMEText(
            f"Echo automated backup - {stamp}\n"
            f"Files: {added}\n"
            f"Encrypted with AES256 GPG.\n"
            f"Passphrase stored in golem.env as BACKUP_PASSPHRASE.\n",
            "plain",
        )
    )
    with enc_path.open("rb") as handle:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(handle.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={enc_path.name}")
    msg.attach(part)
    return msg


def send_gmail(
    gmail_user: str,
    gmail_app_password: str,
    backup_email: str,
    stamp: str,
    added: int,
    enc_path: Path,
    simulate_timeout: bool = False,
) -> None:
    if simulate_timeout:
        raise TimeoutError("simulated SMTP timeout")
    msg = compose_message(gmail_user, backup_email, stamp, added, enc_path)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, backup_email, msg.as_string())


def backoff_for_attempt(attempt: int) -> int:
    index = max(0, min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1))
    return RETRY_BACKOFF_SECONDS[index]


def mark_delivery_pending(status: dict[str, Any], error: Exception) -> dict[str, Any]:
    attempts = int(status.get("delivery_attempts") or 0)
    next_retry = utcnow() + timedelta(seconds=backoff_for_attempt(max(1, attempts)))
    return record_status(
        status,
        stage="offsite_delivery_pending",
        offsite_delivery_pending=True,
        offsite_delivery_succeeded=False,
        offsite_delivery_failed=True,
        last_error=str(error),
        next_retry_at=next_retry.isoformat(timespec="seconds"),
    )


def mark_delivery_success(status: dict[str, Any], enc_path: Path) -> dict[str, Any]:
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    sent_path = SENT_DIR / enc_path.name
    if enc_path.exists():
        shutil.move(str(enc_path), sent_path)
    LAST_BACKUP_FILE.write_text(datetime.now().isoformat())
    return record_status(
        status,
        stage="offsite_delivery_succeeded",
        artifact_path=relative(sent_path),
        offsite_delivery_pending=False,
        offsite_delivery_succeeded=True,
        offsite_delivery_failed=False,
        next_retry_at=None,
        last_error=None,
        delivered_at=iso_now(),
    )


def deliver_with_retries(
    status: dict[str, Any],
    env: dict[str, str],
    local_only: bool = False,
    simulate_timeout: bool = False,
    sleep_between_retries: bool = True,
) -> dict[str, Any]:
    if status.get("offsite_delivery_succeeded"):
        log("Offsite delivery already succeeded; duplicate send prevented")
        return status

    artifact = status.get("artifact_path")
    if not artifact:
        raise BackupStageError("encrypted artifact path missing before delivery")
    enc_path = BASE / artifact
    if not enc_path.exists():
        raise BackupStageError(f"encrypted artifact missing: {artifact}")

    if local_only:
        log("Local backup/encryption complete; offsite delivery left pending by local-only mode")
        return record_status(
            status,
            stage="offsite_delivery_pending",
            offsite_delivery_pending=True,
            offsite_delivery_succeeded=False,
            offsite_delivery_failed=False,
        )

    gmail_user = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER") or os.environ.get("GMAIL_ADDRESS", "")
    gmail_app_password = env.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD", "")
    backup_email = env.get("BACKUP_EMAIL") or env.get("GMAIL_ADDRESS") or gmail_user
    if not gmail_user or not gmail_app_password:
        raise BackupStageError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in golem.env")

    added = int(status.get("files_added") or 0)
    stamp = str(status.get("stamp") or datetime.now().strftime("%Y%m%d_%H%M"))
    while int(status.get("delivery_attempts") or 0) < MAX_DELIVERY_ATTEMPTS:
        attempt = int(status.get("delivery_attempts") or 0) + 1
        record_status(
            status,
            stage="offsite_delivery_attempt",
            delivery_attempts=attempt,
            last_attempt_at=iso_now(),
        )
        try:
            send_gmail(
                gmail_user,
                gmail_app_password,
                backup_email,
                stamp,
                added,
                enc_path,
                simulate_timeout=simulate_timeout,
            )
            log(f"Backup emailed to {backup_email}")
            status = mark_delivery_success(status, enc_path)
            try:
                from core.event_ledger import log_event

                log_event("system", "offsite_backup", f"backup emailed: {added} files", score=1.0)
            except Exception:
                pass
            return status
        except Exception as exc:
            log(f"Email send failed on attempt {attempt}: {exc}")
            status = mark_delivery_pending(status, exc)
            if attempt >= MAX_DELIVERY_ATTEMPTS:
                return status
            if sleep_between_retries:
                time.sleep(min(backoff_for_attempt(attempt), 5))
    return status


def create_local_encrypted_backup(env: dict[str, str], stamp: str | None = None) -> dict[str, Any]:
    gpg_passphrase = env.get("BACKUP_PASSPHRASE") or os.environ.get("BACKUP_PASSPHRASE", "")
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    status = base_status(stamp)
    if not gpg_passphrase:
        record_status(status, stage="encryption_failed", last_error="BACKUP_PASSPHRASE not set")
        raise BackupStageError("BACKUP_PASSPHRASE not set in golem.env - refusing to encrypt with default")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        archive_path, added = create_archive(stamp, tmpdir)
        status = record_status(
            status,
            stage="local_backup_created",
            local_backup_created=True,
            archive_size_bytes=archive_path.stat().st_size,
            files_added=added,
        )
        enc_path = encrypt_archive(archive_path, gpg_passphrase)
        status = record_status(
            status,
            stage="encryption_completed",
            encryption_completed=True,
            artifact_path=relative(enc_path),
            encrypted_size_bytes=enc_path.stat().st_size,
            offsite_delivery_pending=True,
        )
    return status


def run(
    local_only: bool = False,
    simulate_smtp_timeout: bool = False,
    force_new: bool = False,
    sleep_between_retries: bool = True,
) -> dict[str, Any]:
    log("Offsite backup starting")
    env = load_env()
    status = load_status()

    if pending_status_is_reusable(status) and not force_new:
        if not due_for_retry(status):
            log(f"Pending encrypted backup not due for retry until {status.get('next_retry_at')}")
            return status
        log(f"Retrying pending encrypted backup: {status.get('artifact_path')}")
    else:
        status = create_local_encrypted_backup(env)

    status = deliver_with_retries(
        status,
        env,
        local_only=local_only,
        simulate_timeout=simulate_smtp_timeout,
        sleep_between_retries=sleep_between_retries,
    )
    if status.get("offsite_delivery_succeeded"):
        log("Offsite backup complete")
    else:
        log(f"Offsite delivery pending; encrypted artifact preserved at {status.get('artifact_path')}")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true", help="create/encrypt backup but do not send")
    parser.add_argument("--simulate-smtp-timeout", action="store_true")
    parser.add_argument("--force-new", action="store_true")
    parser.add_argument("--no-sleep", action="store_true")
    parser.add_argument("--print-status", action="store_true")
    args = parser.parse_args()

    try:
        status = run(
            local_only=args.local_only,
            simulate_smtp_timeout=args.simulate_smtp_timeout,
            force_new=args.force_new,
            sleep_between_retries=not args.no_sleep,
        )
    except BackupStageError as exc:
        log(f"ERROR: {exc}")
        return 1

    if args.print_status:
        print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
