from __future__ import annotations
import os, json, hashlib, time
from pathlib import Path

ROOT = Path.cwd()
OUT_DIR = ROOT / "bundles_raw"
OUT_DIR.mkdir(exist_ok=True)

# Maximize part size but keep under 100MB
MAX_BYTES_PER_PART = 99 * 1024 * 1024  # 99MB

# Toggles
INCLUDE_MEMORY_DIR = False   # set True if you want memory/* bundled
INCLUDE_LOGS_DIR = False     # set True if you want logs/* bundled
INCLUDE_SECRETS = False      # set True if you want appkey/.env/etc included

# Include extensions
INCLUDE_EXT = {
    ".py",".sh",".md",".txt",".json",".yml",".yaml",".toml",".ini",".cfg",".log"
}

# Exclude dirs (path segments)
EXCLUDE_DIRS = {
    ".git","__pycache__","venv",".venv","node_modules","backup_project","bundles","bundles_raw"
}
if not INCLUDE_MEMORY_DIR:
    EXCLUDE_DIRS.add("memory")
if not INCLUDE_LOGS_DIR:
    EXCLUDE_DIRS.add("logs")

# Exclude binary-ish extensions
EXCLUDE_EXT = {
    ".png",".jpg",".jpeg",".gif",".webp",".mp4",".mov",".pdf",
    ".bin",".so",".zip",".tar",".gz",".7z",".sqlite",".db",".pyc"
}

# Exclude likely secret file names (unless INCLUDE_SECRETS=True)
SECRET_NAMES = {
    "appkey.txt",".env",".env.local",".envrc",
    "id_rsa","id_ed25519",
    "robinhood_config.json",
}
# Also exclude huge key dumps if any:
SECRET_SUBSTRINGS = ["secret", "token", "apikey", "api_key", "private_key"]

def sha256_stream(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def should_exclude(rel: Path) -> tuple[bool, str]:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        return True, "excluded_dir"
    if rel.suffix.lower() in EXCLUDE_EXT:
        return True, "excluded_ext"
    if rel.is_symlink():
        return True, "symlink"
    if rel.suffix.lower() not in INCLUDE_EXT:
        return True, "not_included_ext"
    if not INCLUDE_SECRETS:
        if rel.name in SECRET_NAMES:
            return True, "secret_name"
        low = str(rel).lower()
        if any(s in low for s in SECRET_SUBSTRINGS):
            # comment this out if it's too aggressive
            pass
    return False, ""

def iter_files():
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(ROOT)
        ex, _ = should_exclude(rel)
        if ex:
            continue
        yield p

def new_part_header():
    return (
        "ECHO RAW BUNDLE (multi-part)\n"
        f"Generated: {time.ctime()}\n"
        f"Root: {ROOT}\n"
        f"MAX_BYTES_PER_PART: {MAX_BYTES_PER_PART}\n\n"
    )

def write_part(idx: int, buf: bytearray) -> Path:
    out = OUT_DIR / f"echo_bundle_raw_part_{idx:03d}.txt"
    out.write_bytes(buf)
    return out

def main():
    manifest = {
        "generated_at": time.ctime(),
        "root": str(ROOT),
        "max_bytes_per_part": MAX_BYTES_PER_PART,
        "include_memory_dir": INCLUDE_MEMORY_DIR,
        "include_logs_dir": INCLUDE_LOGS_DIR,
        "include_secrets": INCLUDE_SECRETS,
        "parts": [],
        "files": []
    }

    part_idx = 1
    buf = bytearray(new_part_header().encode("utf-8"))
    buf_bytes = len(buf)

    files = sorted(iter_files(), key=lambda x: str(x))
    for p in files:
        rel = p.relative_to(ROOT)
        size = p.stat().st_size
        sha = sha256_stream(p)

        manifest["files"].append({"path": str(rel), "bytes": size, "sha256": sha})

        # Write file header (always)
        header = (
            f"\n\n===== FILE: {rel} =====\n"
            f"SIZE_BYTES: {size}\n"
            f"SHA256: {sha}\n"
            "----- BEGIN CONTENT -----\n"
        ).encode("utf-8")

        footer = "\n----- END CONTENT -----\n".encode("utf-8")

        # If header doesn't fit, flush part
        if buf_bytes + len(header) > MAX_BYTES_PER_PART:
            outp = write_part(part_idx, buf)
            manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})
            part_idx += 1
            buf = bytearray(new_part_header().encode("utf-8"))
            buf_bytes = len(buf)

        buf.extend(header)
        buf_bytes += len(header)

        # Stream file content and split across parts if needed
        with p.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)  # 1MB
                if not chunk:
                    break

                # If chunk won't fit, flush current part and continue
                if buf_bytes + len(chunk) > MAX_BYTES_PER_PART:
                    outp = write_part(part_idx, buf)
                    manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})
                    part_idx += 1
                    buf = bytearray(new_part_header().encode("utf-8"))
                    buf_bytes = len(buf)

                    # mark continuation
                    cont = f"\n\n===== CONTINUATION OF: {rel} =====\n".encode("utf-8")
                    if buf_bytes + len(cont) > MAX_BYTES_PER_PART:
                        # extremely unlikely
                        continue
                    buf.extend(cont)
                    buf_bytes += len(cont)

                buf.extend(chunk)
                buf_bytes += len(chunk)

        # footer
        if buf_bytes + len(footer) > MAX_BYTES_PER_PART:
            outp = write_part(part_idx, buf)
            manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})
            part_idx += 1
            buf = bytearray(new_part_header().encode("utf-8"))
            buf_bytes = len(buf)

        buf.extend(footer)
        buf_bytes += len(footer)

    # final flush
    outp = write_part(part_idx, buf)
    manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (OUT_DIR / "README.txt").write_text(
        "RAW bundle created. Parts are <= ~99MB.\n"
        "Share parts + manifest.json with the other AI.\n"
        "WARNING: may contain secrets if you enabled INCLUDE_SECRETS.\n"
    )

    print("Wrote:", OUT_DIR)
    for prt in manifest["parts"]:
        print(" ", prt["file"], prt["bytes"], "bytes")
    print("Files bundled:", len(manifest["files"]))

if __name__ == "__main__":
    main()
