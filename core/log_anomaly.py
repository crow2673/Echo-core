#!/usr/bin/env python3
"""
core/log_anomaly.py — LSTM next-event anomaly detector for Echo's logs.

My half of the log-anomaly build (collab bus #107/#108/#109). Codex owns
core/log_keys.py (templating) + core/log_sequences.py (windowing) + the
dispatcher/timer wiring; this module owns the model, training, and the
rank-based anomaly critic (DeepLog/DabLog, Ch.4 of the AI-for-Cybersecurity
handbook).

Idea: train an LSTM on NORMAL (window -> next-event) pairs. At score time, if
the event that actually followed a window is not among the model's top-N
predictions (rank-based criterion), the window is flagged anomalous — a
deviation from learned-normal behavior (possible intrusion/failure).

Consumes Codex's core.log_sequences.build_from_logs(since, seqlen), whose
payload is {key_to_index, index_to_key, sequences:[{source, ts, input:[ids],
target:id, target_key, raw_hash}]}. Indices start at 1; PAD=0 is reserved.

Commands (CPU-only by design — never competes with ollama for the GPU):
    python3 -m core.log_anomaly train     [--since "72 hours ago"] [--seqlen 10] [--epochs 8]
    python3 -m core.log_anomaly score     [--since "30 minutes ago"] [--topn 9]
    python3 -m core.log_anomaly self-test    # synthetic data; no log deps
"""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE / "memory" / "log_anomaly_model.pt"
FINDINGS_PATH = BASE / "memory" / "log_anomaly_findings.json"
LOG_PATH = BASE / "logs" / "log_anomaly.log"

EMB_DIM = 64
HIDDEN = 64
PAD = 0


def log(msg: str):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def _torch():
    import torch
    torch.set_num_threads(2)          # good neighbor on a shared box
    torch.manual_seed(0)
    return torch


def _make_model(torch, vocab_size: int):
    nn = torch.nn

    class LogLSTM(nn.Module):
        def __init__(self, v):
            super().__init__()
            self.embed = nn.Embedding(v, EMB_DIM, padding_idx=PAD)
            self.lstm = nn.LSTM(EMB_DIM, HIDDEN, num_layers=2, batch_first=True)
            self.out = nn.Linear(HIDDEN, v)

        def forward(self, x):
            h, _ = self.lstm(self.embed(x))
            return self.out(h[:, -1, :])   # predict the next event from the window

    return LogLSTM(vocab_size)


def _load_payload(
    since: str,
    seqlen: int,
    max_files: int = 80,
    max_lines_per_file: int = 300,
    max_journal_lines: int = 1000,
    max_events: int = 5000,
    max_sequences: int = 8000,
    include_journal: bool = True,
    deadline_at: float | None = None,
) -> dict:
    """Get Codex's sequence payload; clear error if his half isn't importable."""
    try:
        from core.log_sequences import build_from_logs
    except Exception as e:
        raise SystemExit(
            "core.log_sequences.build_from_logs not available "
            f"(Codex's half). Run `python3 -m core.log_anomaly self-test` to validate. ({e})"
        )
    return build_from_logs(
        since=since,
        seqlen=seqlen,
        max_files=max_files,
        max_lines_per_file=max_lines_per_file,
        max_journal_lines=max_journal_lines,
        max_events=max_events,
        max_sequences=max_sequences,
        include_journal=include_journal,
        deadline_at=deadline_at,
    )


# ─────────────────────────── model train/score on (window -> target) ───────────────────────────
def _train_records(torch, records, vsize, epochs=8, lr=1e-3, batch=128):
    import torch.nn.functional as F
    X = torch.tensor([r["input"] for r in records], dtype=torch.long)
    y = torch.tensor([r["target"] for r in records], dtype=torch.long)
    model = _make_model(torch, vsize)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    model.train()
    n = X.shape[0]
    for ep in range(epochs):
        perm = torch.randperm(n)
        total = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            loss = F.cross_entropy(model(X[idx]), y[idx])
            opt.zero_grad(); loss.backward(); opt.step()
            total += loss.item() * idx.shape[0]
        log(f"[train] epoch {ep+1}/{epochs} loss={total/n:.4f}")
    return model


def _critic(torch, model, records, topn, deadline_at: float | None = None, batch_size: int = 256):
    """Rank-based critic: flag records whose actual target isn't in the model's top-N."""
    findings = []
    processed = 0
    deadline_reached = False
    model.eval()
    with torch.no_grad():
        X = torch.tensor([r["input"] for r in records], dtype=torch.long)
        for i in range(0, X.shape[0], batch_size):
            if deadline_at and time.monotonic() >= deadline_at:
                deadline_reached = True
                break
            logits = model(X[i:i + batch_size])
            topk = logits.topk(min(topn, logits.shape[-1]), dim=-1).indices.tolist()
            for j, top in enumerate(topk):
                r = records[i + j]
                processed += 1
                if r["target"] != PAD and r["target"] not in top:
                    findings.append({
                        "source": r.get("source", "?"),
                        "ts": r.get("ts", ""),
                        "seq": r["input"],
                        "target": r["target"],
                        "target_key": r.get("target_key", ""),
                        "n_anom": 1,
                    })
    return findings, {"processed": processed, "deadline_reached": deadline_reached}


def train(since="72 hours ago", seqlen=10, epochs=8):
    torch = _torch()
    payload = _load_payload(since, seqlen)
    records = payload["sequences"]
    vsize = len(payload["key_to_index"]) + 1     # +1 for PAD
    if not records:
        raise SystemExit("no sequences to train on (try a wider --since)")
    log(f"[train] {len(records)} windows, vocab={vsize}, seqlen={seqlen}, since={since!r}")
    model = _train_records(torch, records, vsize, epochs=epochs)
    torch.save({"state": model.state_dict(), "vocab": vsize, "seqlen": seqlen,
                "key_to_index": payload["key_to_index"],
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "n_train": len(records)}, MODEL_PATH)
    log(f"[train] saved model -> {MODEL_PATH}")
    return True


def _finding_key(f) -> str:
    return hashlib.sha256(f"{f['source']}|{f['seq']}|{f['target']}".encode()).hexdigest()[:16]


def _stage(started: float, name: str) -> None:
    log(f"[score] stage={name} elapsed={time.monotonic() - started:.1f}s")


def score(
    since="30 minutes ago",
    topn=0,
    notify=True,
    max_files=80,
    max_lines_per_file=120,
    max_journal_lines=500,
    max_events=5000,
    max_sequences=8000,
    deadline_seconds=180,
    include_journal=True,
):
    started = time.monotonic()
    deadline_at = started + max(10, int(deadline_seconds)) if deadline_seconds else None
    torch = _torch()
    if not MODEL_PATH.exists():
        raise SystemExit("no trained model — run `python3 -m core.log_anomaly train` first")
    ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    _stage(started, "model_loaded")
    # topn<=0 -> book's rank-threshold criterion: anomalous if not in the top 5% of vocab.
    if topn <= 0:
        topn = max(9, int(0.05 * ckpt["vocab"]))
    model = _make_model(torch, ckpt["vocab"])
    model.load_state_dict(ckpt["state"])
    _stage(started, "model_ready")
    payload = _load_payload(
        since,
        ckpt.get("seqlen", 10),
        max_files=max_files,
        max_lines_per_file=max_lines_per_file,
        max_journal_lines=max_journal_lines,
        max_events=max_events,
        max_sequences=max_sequences,
        include_journal=include_journal,
        deadline_at=deadline_at,
    )
    _stage(started, "sequences_built")

    # core.log_sequences re-derives indices per build, so remap score-time records
    # into the TRAINED index space via the stable template-key strings. A target
    # whose template was never seen in training is a novel event -> anomalous outright.
    trained = ckpt.get("key_to_index", {})
    s_idx2key = payload.get("index_to_key", {})
    findings, remapped = [], []
    for r in payload["sequences"]:
        if deadline_at and time.monotonic() >= deadline_at:
            break
        mapped_input = [trained.get(s_idx2key.get(str(i), ""), PAD) for i in r["input"]]
        tkey = r.get("target_key") or s_idx2key.get(str(r["target"]), "")
        if tkey not in trained:
            findings.append({"source": r.get("source", "?"), "ts": r.get("ts", ""),
                             "seq": mapped_input, "target": -1, "target_key": tkey,
                             "n_anom": 1, "novel": True})
        else:
            remapped.append({**r, "input": mapped_input, "target": trained[tkey]})
    _stage(started, "records_remapped")
    critic_findings, critic_meta = _critic(torch, model, remapped, topn, deadline_at=deadline_at)
    findings += critic_findings
    _stage(started, "records_scored")

    prior = {}
    if FINDINGS_PATH.exists():
        try:
            prior = {f["key"]: f for f in json.loads(FINDINGS_PATH.read_text()).get("findings", [])}
        except Exception:
            pass
    new = []
    for f in findings:
        f["key"] = _finding_key(f)
        f["detected_at"] = datetime.now(timezone.utc).isoformat()
        if f["key"] not in prior:
            new.append(f)

    all_f = list(prior.values()) + new
    metadata = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "since": since,
        "limits": {
            "max_files": max_files,
            "max_lines_per_file": max_lines_per_file,
            "max_journal_lines": max_journal_lines,
            "max_events": max_events,
            "max_sequences": max_sequences,
            "deadline_seconds": deadline_seconds,
        },
        "events": payload.get("event_count"),
        "sources": payload.get("source_count"),
        "windows": len(payload["sequences"]),
        "remapped": len(remapped),
        "critic_processed": critic_meta["processed"],
        "partial": bool(payload.get("bounds", {}).get("sequence_limit_reached") or payload.get("bounds", {}).get("deadline_reached") or critic_meta["deadline_reached"]),
        "bounds": payload.get("bounds", {}),
    }
    FINDINGS_PATH.write_text(json.dumps(
        {"updated": metadata["updated"], "metadata": metadata, "findings": all_f[-500:]}, indent=2))
    log(
        "[score] "
        f"{len(payload['sequences'])} windows available, {critic_meta['processed']} model-scored, "
        f"{len(findings)} anomalous, {len(new)} NEW, partial={metadata['partial']}"
    )

    if new and notify and os.environ.get("ECHO_LOG_ANOMALY_TELEGRAM", "").lower() in ("1", "true", "yes"):
        try:
            from core.notifier import notify as _n
            srcs = {}
            for f in new:
                srcs[f["source"]] = srcs.get(f["source"], 0) + 1
            summary = "; ".join(f"{s} ×{c}" for s, c in sorted(srcs.items(), key=lambda x: -x[1])[:3])
            _n("Echo: log anomaly", f"{len(new)} new anomalous log window(s): {summary}", urgent=False)
        except Exception as e:
            log(f"[score] notify failed: {e}")
    elif new and notify:
        log("[score] telegram notification suppressed by default; set ECHO_LOG_ANOMALY_TELEGRAM=1 to enable")
    return new


# ─────────────────────────── self-test (no log deps) ───────────────────────────
def self_test():
    """Validate model+critic on synthetic (window -> target) records.
    Normal = the cycle 1→2→3→4 repeating; anomaly = a target that breaks it."""
    torch = _torch()
    V = 8
    base = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2]
    normal = [{"input": base, "target": 3, "source": "normal"} for _ in range(300)]
    model = _train_records(torch, normal, V, epochs=15)
    test = [{"input": base, "target": 3, "source": "normal"},     # expected next
            {"input": base, "target": 7, "source": "ANOMALY"}]    # out-of-pattern next
    findings, _meta = _critic(torch, model, test, topn=2)
    log(f"[self-test] findings: {json.dumps(findings)}")
    ok = (len(findings) == 1 and findings[0]["source"] == "ANOMALY")
    log(f"[self-test] {'PASS' if ok else 'FAIL'} — flagged the broken continuation, ignored normal")
    return ok


def bounded_self_test():
    """Prove the critic can stop early and still return a clean partial result."""
    torch = _torch()
    V = 12
    base = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    normal = [{"input": base, "target": 3, "source": "normal"} for _ in range(80)]
    model = _train_records(torch, normal, V, epochs=2)
    records = [{"input": base, "target": 11, "source": "bounded"} for _ in range(200)]
    findings, meta = _critic(torch, model, records, topn=2, deadline_at=time.monotonic() - 0.001)
    ok = meta["processed"] == 0 and meta["deadline_reached"] and findings == []
    log(f"[bounded-self-test] {'PASS' if ok else 'FAIL'} meta={json.dumps(meta)}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train"); t.add_argument("--since", default="72 hours ago")
    t.add_argument("--seqlen", type=int, default=10); t.add_argument("--epochs", type=int, default=8)
    s = sub.add_parser("score"); s.add_argument("--since", default="30 minutes ago")
    s.add_argument("--topn", type=int, default=0, help="0 = auto (top 5%% of vocab, per the book)")
    s.add_argument("--no-notify", action="store_true")
    s.add_argument("--max-files", type=int, default=80)
    s.add_argument("--max-lines-per-file", type=int, default=120)
    s.add_argument("--max-journal-lines", type=int, default=500)
    s.add_argument("--max-events", type=int, default=5000)
    s.add_argument("--max-sequences", type=int, default=8000)
    s.add_argument("--deadline-seconds", type=int, default=180)
    s.add_argument("--no-journal", action="store_true")
    sub.add_parser("self-test")
    sub.add_parser("bounded-self-test")
    a = ap.parse_args()

    if a.cmd == "train":
        train(since=a.since, seqlen=a.seqlen, epochs=a.epochs)
    elif a.cmd == "score":
        score(
            since=a.since,
            topn=a.topn,
            notify=not a.no_notify,
            max_files=a.max_files,
            max_lines_per_file=a.max_lines_per_file,
            max_journal_lines=a.max_journal_lines,
            max_events=a.max_events,
            max_sequences=a.max_sequences,
            deadline_seconds=a.deadline_seconds,
            include_journal=not a.no_journal,
        )
    elif a.cmd == "self-test":
        raise SystemExit(0 if self_test() else 1)
    elif a.cmd == "bounded-self-test":
        raise SystemExit(0 if bounded_self_test() else 1)


if __name__ == "__main__":
    main()
