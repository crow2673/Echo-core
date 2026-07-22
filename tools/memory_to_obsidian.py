#!/usr/bin/env python3
"""
tools/memory_to_obsidian.py — export Echo's memory as an Obsidian vault.

Each memory (and each memory/*.md note) becomes a markdown note. Edges are
SEMANTIC: every note links to its most-similar neighbours via [[wikilinks]],
computed from the 384-dim sentence embeddings Echo already stores. Open the
output folder as an Obsidian vault and the graph view shows how her thoughts
cluster and relate.

Sources:
  - ~/Echo/echo_semantic_memory.sqlite   (memories table: text + embedding BLOB)
  - ~/Echo/memory/*.md                   (her written notes; embedded on the fly)

Usage:
  python3 tools/memory_to_obsidian.py
  python3 tools/memory_to_obsidian.py --out ~/EchoBrain --limit 1500 --top-k 6 --min-sim 0.45
"""
import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np

HOME = Path.home()
SEM_DB = HOME / "Echo/echo_semantic_memory.sqlite"
NOTES_DIR = HOME / "Echo/memory"
DEFAULT_OUT = HOME / "Echo/memory/obsidian_vault"


def _slug(text: str, n: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].rstrip("-")) or "note"


def _title(text: str) -> str:
    """A short human title from a memory's text (the User: line, if present)."""
    first = text.strip().splitlines()[0] if text.strip() else "memory"
    first = re.sub(r"^(User|Echo):\s*", "", first).strip()
    words = first.split()
    return " ".join(words[:9]) + ("…" if len(words) > 9 else "")


def load_memories(limit: int | None, exclude_kinds: set[str]) -> list[dict]:
    if not SEM_DB.exists():
        return []
    db = sqlite3.connect(str(SEM_DB))
    # Pull newest-first; we filter in Python so `limit` counts *kept* (signal) rows,
    # not the screen-watcher telemetry that otherwise drowns the graph.
    rows = db.execute(
        "SELECT id, text, embedding, metadata, created_at FROM memories ORDER BY id DESC"
    ).fetchall()
    db.close()
    out, seen = [], set()
    for mid, text, emb, meta, created in rows:
        vec = np.frombuffer(emb, dtype=np.float32)
        if vec.shape[0] != 384:
            continue
        md = {}
        try:
            md = json.loads(meta) if meta else {}
        except Exception:
            pass
        if md.get("type", "memory") in exclude_kinds:
            continue
        norm = re.sub(r"\s+", " ", text.strip().lower())  # exact-ish dedup
        if norm in seen:
            continue
        seen.add(norm)
        out.append({
            "name": f"mem-{mid}-{_slug(_title(text))}",
            "title": _title(text),
            "text": text,
            "vec": vec,
            "source": md.get("source", "memory"),
            "kind": md.get("type", "memory"),
            "created": (created or "")[:19],
        })
        if limit and len(out) >= limit:
            break
    return out


def load_notes(embed_fn) -> list[dict]:
    """Embed her markdown notes so they join the same semantic graph."""
    out = []
    for p in sorted(NOTES_DIR.glob("*.md")):
        body = p.read_text(errors="ignore").strip()
        if len(body) < 20:
            continue
        out.append({
            "name": f"note-{_slug(p.stem)}",
            "title": p.stem.replace("_", " "),
            "text": body,
            "vec": embed_fn(body[:1000]),
            "source": "note",
            "kind": "note",
            "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat()[:19],
        })
    return out


def link_graph(nodes: list[dict], top_k: int, min_sim: float) -> list[list[tuple[int, float]]]:
    """For each node return [(neighbor_idx, sim), ...] — its strongest semantic edges."""
    mat = np.vstack([n["vec"] for n in nodes]).astype(np.float32)
    # embeddings are L2-normalized → cosine similarity is just the dot product
    sims = mat @ mat.T
    np.fill_diagonal(sims, -1.0)
    neighbors = []
    for i in range(len(nodes)):
        idx = np.argsort(-sims[i])[:top_k]
        neighbors.append([(int(j), float(sims[i][j])) for j in idx if sims[i][j] >= min_sim])
    return neighbors


def write_vault(nodes, neighbors, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for i, node in enumerate(nodes):
        lines = [
            "---",
            f"created: {node['created']}",
            f"source: {node['source']}",
            f"kind: {node['kind']}",
            "---",
            "",
            f"# {node['title']}",
            "",
            node["text"],
            "",
            "## Related",
        ]
        if neighbors[i]:
            for j, sim in neighbors[i]:
                lines.append(f"- [[{nodes[j]['name']}]] · {sim:.2f}")
        else:
            lines.append("- (no strong links)")
        (out / f"{node['name']}.md").write_text("\n".join(lines) + "\n")

    # An entry-point index so the vault opens somewhere sensible.
    edges = sum(len(n) for n in neighbors)
    idx = [
        "---", "kind: index", "---", "",
        "# Echo's Mind",
        "",
        f"Exported {datetime.now().isoformat()[:19]} · {len(nodes)} notes · {edges} semantic links.",
        "",
        "Open Graph View (Ctrl/Cmd-G) to explore. Clusters = related thoughts.",
        "",
        "## Most-connected memories",
    ]
    conn_counts = sorted(range(len(nodes)), key=lambda i: -len(neighbors[i]))[:15]
    for i in conn_counts:
        idx.append(f"- [[{nodes[i]['name']}]] ({len(neighbors[i])} links) — {nodes[i]['title']}")
    (out / "_Echo's Mind.md").write_text("\n".join(idx) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=0, help="max kept memories (newest first); 0 = all")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--min-sim", type=float, default=0.45)
    ap.add_argument("--no-notes", action="store_true", help="skip embedding the markdown notes")
    ap.add_argument("--exclude-kinds", default="screen_context",
                    help="comma-separated memory kinds to drop as noise (default: screen_context)")
    ap.add_argument("--include-screen", action="store_true",
                    help="keep screen_context telemetry (overrides --exclude-kinds)")
    a = ap.parse_args()

    exclude = set() if a.include_screen else {k.strip() for k in a.exclude_kinds.split(",") if k.strip()}
    nodes = load_memories(a.limit or None, exclude)
    if not a.no_notes:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        embed = lambda t: np.asarray(model.encode(t, normalize_embeddings=True), dtype=np.float32)
        nodes += load_notes(embed)

    if not nodes:
        print("No memories found — is echo_semantic_memory.sqlite populated?")
        return

    neighbors = link_graph(nodes, a.top_k, a.min_sim)
    out = Path(a.out).expanduser()
    write_vault(nodes, neighbors, out)
    edges = sum(len(n) for n in neighbors)
    print(f"Vault written: {out}")
    print(f"  {len(nodes)} notes, {edges} semantic links")
    print(f"  Open this folder as an Obsidian vault → Graph View.")


if __name__ == "__main__":
    main()
