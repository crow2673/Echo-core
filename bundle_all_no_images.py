from __future__ import annotations
import json, hashlib, time
from pathlib import Path

ROOT = Path.cwd()
OUT_DIR = ROOT / "bundles_all_no_images"
OUT_DIR.mkdir(exist_ok=True)

MAX_BYTES_PER_PART = 99 * 1024 * 1024  # ~99MB per part

# Exclude only images/screenshots
EXCLUDE_IMAGE_EXT = {".png",".jpg",".jpeg",".gif",".webp",".bmp",".tiff",".ico"}

# Still exclude these dirs (otherwise you’ll explode size with venv/.git/node_modules)
EXCLUDE_DIRS = {".git","venv",".venv","node_modules","__pycache__","bundles_all_no_images"}

# If you truly want “everything”, set this True (NOT recommended for cloud)
INCLUDE_SECRETS = False

SECRET_NAMES = {"appkey.txt",".env",".env.local",".envrc","id_rsa","id_ed25519","robinhood_config.json"}

def sha256_stream(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def is_binary_bytes(b: bytes) -> bool:
    # crude but effective: NUL byte usually means binary
    return b"\x00" in b

def new_part_header():
    return (
        "ECHO BUNDLE (ALL TEXT EXCEPT IMAGES)\n"
        f"Generated: {time.ctime()}\n"
        f"Root: {ROOT}\n"
        f"MAX_BYTES_PER_PART: {MAX_BYTES_PER_PART}\n"
        f"INCLUDE_SECRETS: {INCLUDE_SECRETS}\n\n"
    ).encode("utf-8")

def write_part(idx: int, buf: bytearray) -> Path:
    out = OUT_DIR / f"echo_bundle_part_{idx:03d}.txt"
    out.write_bytes(buf)
    return out

def main():
    manifest = {
        "generated_at": time.ctime(),
        "root": str(ROOT),
        "max_bytes_per_part": MAX_BYTES_PER_PART,
        "include_secrets": INCLUDE_SECRETS,
        "parts": [],
        "files_included": [],
        "files_skipped": [],  # {path, reason, bytes, sha256}
    }

    part_idx = 1
    buf = bytearray(new_part_header())
    buf_bytes = len(buf)

    for p in sorted(ROOT.rglob("*"), key=lambda x: str(x)):
        if p.is_dir():
            continue
        rel = p.relative_to(ROOT)

        if any(seg in EXCLUDE_DIRS for seg in rel.parts):
            continue
        if rel.is_symlink():
            manifest["files_skipped"].append({"path": str(rel), "reason": "symlink"})
            continue
        if rel.suffix.lower() in EXCLUDE_IMAGE_EXT:
            continue
        if (not INCLUDE_SECRETS) and rel.name in SECRET_NAMES:
            manifest["files_skipped"].append({"path": str(rel), "reason": "secret_name"})
            continue

        try:
            raw = p.read_bytes()
        except Exception as e:
            manifest["files_skipped"].append({"path": str(rel), "reason": f"read_error:{e}"})
            continue

        size = len(raw)
        sha = sha256_stream(p)

        if is_binary_bytes(raw):
            manifest["files_skipped"].append({"path": str(rel), "reason": "binary", "bytes": size, "sha256": sha})
            continue

        # decode to text (replace errors)
        text = raw.decode("utf-8", errors="replace")

        block = (
            f"\n\n===== FILE: {rel} =====\n"
            f"SIZE_BYTES: {size}\n"
            f"SHA256: {sha}\n"
            "----- BEGIN CONTENT -----\n"
            f"{text}\n"
            "----- END CONTENT -----\n"
        ).encode("utf-8")

        # roll part if needed
        if buf_bytes + len(block) > MAX_BYTES_PER_PART:
            outp = write_part(part_idx, buf)
            manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})
            part_idx += 1
            buf = bytearray(new_part_header())
            buf_bytes = len(buf)

        buf.extend(block)
        buf_bytes += len(block)
        manifest["files_included"].append({"path": str(rel), "bytes": size, "sha256": sha})

    outp = write_part(part_idx, buf)
    manifest["parts"].append({"part": part_idx, "file": str(outp.relative_to(ROOT)), "bytes": outp.stat().st_size})

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (OUT_DIR / "README.txt").write_text(
        "Bundle created: all text-readable files except images.\n"
        "Binary files were skipped and listed in manifest.json.\n"
        "If you need secrets included, set INCLUDE_SECRETS=True and rerun (not recommended for cloud).\n"
    )

    print("Wrote:", OUT_DIR)
    for prt in manifest["parts"]:
        print(" ", prt["file"], prt["bytes"], "bytes")
    print("Included files:", len(manifest["files_included"]))
    print("Skipped files:", len(manifest["files_skipped"]))

if __name__ == "__main__":
    main()
