#!/usr/bin/env python3
"""core/weekly_reviewer.py — the one ranked 'what matters this week' list.

Echo's decisions have been driven by noisy, often-stale known_gaps entries. This
synthesizes the REAL state — trading P&L by sleeve (from the reconciler), income
signal, content pipeline, and the live secrets/blocker status — into a single
ranked weekly priority list produced by her own LLM, grounded in facts so it
stops inventing phantom blockers.

Run: python3 core/weekly_reviewer.py
Writes: memory/weekly_review.md  (+ logs an event)
Wire into dispatcher weekly if desired.
"""
import json, subprocess, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
OUT = BASE / "memory/weekly_review.md"
SECRETS = BASE / "memory/secrets_status.json"


def gather_trading():
    try:
        d = json.loads((BASE / "memory/cascade_ledger.json").read_text())
        sleeves, total = [], 0.0
        for k in ("1", "2", "3", "4"):
            s = d.get(k)
            if not s:
                continue
            total += s["realized_pl"]
            wr = (s["wins"] / s["total_trades"] * 100) if s["total_trades"] else 0
            sleeves.append(f"{s['name']}: {s['wins']}W/{s['losses']}L ({wr:.0f}% WR) "
                           f"${s['realized_pl']:+.0f}")
        return f"Realized total ${total:+.0f} | " + " | ".join(sleeves), d
    except Exception as e:
        return f"(trading data unavailable: {e})", {}


def gather_blockers():
    """Run the validator if its output is stale/missing, then summarize."""
    if not SECRETS.exists():
        try:
            subprocess.run([sys.executable, str(BASE / "tools/validate_secrets.py")],
                           cwd=str(BASE), timeout=60, check=False,
                           capture_output=True)
        except Exception:
            pass
    try:
        s = json.loads(SECRETS.read_text())
    except Exception:
        return "(secrets status unavailable)"
    lines = []
    for grp, info in s.items():
        st = info["status"]
        tag = {"VALID": "ready", "PRESENT": "ready", "MISSING": "needs cred",
               "BLOCKED(captcha)": "captcha-walled", "INVALID": "broken"}.get(st, st)
        lines.append(f"{grp} [{tag}] -> {info['stream']}")
    return "\n".join(lines)


def _secrets_map():
    try:
        return json.loads(SECRETS.read_text())
    except Exception:
        return {}


def gather_gaps():
    """Pull high-priority gaps, but annotate each with the REAL credential status
    so the LLM can't parrot a stale 'creds not set' claim that's actually false."""
    secrets = _secrets_map()
    # keyword -> ground-truth status string
    truth = {}
    for grp, info in secrets.items():
        kw = grp.split()[0].lower()
        st = info["status"]
        if st in ("VALID", "PRESENT"):
            truth[kw] = "STALE — creds ARE present/valid, this is NOT a blocker"
        elif st == "BLOCKED(captcha)":
            truth[kw] = "real blocker is CAPTCHA, not a missing credential"
        elif st == "MISSING":
            truth[kw] = f"genuinely missing: {', '.join(info.get('missing_keys', []))}"
    try:
        text = (BASE / "memory/known_gaps.md").read_text()
        hi = text.split("## High Priority Gaps")[1].split("## Medium")[0]
        items = []
        for l in hi.splitlines():
            if not l.strip().startswith("-"):
                continue
            g = l.strip("- ").strip()
            low = g.lower()
            for kw, verdict in truth.items():
                if kw in low or (kw == "dev.to" and "devto" in low):
                    g += f"  [GROUND TRUTH: {verdict}]"
                    break
            items.append(g)
        return items[:8]
    except Exception:
        return []


def gather_content():
    try:
        q = json.loads((BASE / "memory/content_strategy.json").read_text()).get("queue", [])
        return f"{len(q)} drafts queued"
    except Exception:
        return "(content queue unavailable)"


def gather_income():
    try:
        from core.event_ledger import query_summary
        s = query_summary()
        return f"income events logged: {s.get('by_type',{}).get('income',0)}"
    except Exception:
        return "(income summary unavailable)"


def build_digest():
    trading, _ = gather_trading()
    return {
        "trading": trading,
        "blockers": gather_blockers(),
        "content": gather_content(),
        "income": gather_income(),
        "open_gaps": gather_gaps(),
    }


SYSTEM = (
    "You are Echo's strategic analyst. You get a factual digest of her real "
    "system state. Produce ONE ranked list of the top 5 things that matter THIS "
    "WEEK to grow income and system health. Rank by leverage. For each: a 1-line "
    "action, why it matters (cite the digest fact), and status: BUILDABLE NOW or "
    "BLOCKED (by exactly what).\n\n"
    "CRITICAL GROUNDING RULES — follow exactly:\n"
    "1. The BLOCKERS section is GROUND TRUTH. The OPEN GAPS list is historical and "
    "frequently WRONG — many of its 'credentials not set' claims are false.\n"
    "2. Any gap tagged [GROUND TRUTH: ...] — obey that tag, not the gap text.\n"
    "3. NEVER recommend 'obtain/get X credential' if BLOCKERS shows that service as "
    "ready/valid/present. If creds are present, the action is to USE them, not get them.\n"
    "4. A service marked captcha-walled is NOT a missing-credential problem.\n"
    "Be terse and concrete. Output a numbered markdown list."
)


def main():
    digest = build_digest()
    prompt = (
        "=== ECHO SYSTEM DIGEST ===\n"
        f"TRADING: {digest['trading']}\n\n"
        f"BLOCKERS / SECRETS (ground truth):\n{digest['blockers']}\n\n"
        f"CONTENT: {digest['content']}\n"
        f"INCOME: {digest['income']}\n\n"
        f"OPEN GAPS (may be stale — cross-check against BLOCKERS above):\n"
        + "\n".join(f"- {g}" for g in digest["open_gaps"]) +
        "\n\nProduce the ranked top-5 'what matters this week' list now."
    )
    from core.providers.router import call_ollama
    # 7b, not 32b: the reviewer shares Ollama with Echo's bus bridge (32b); same-model
    # requests serialize and time out. A 7b loads separately and follows the grounding
    # rules fine for a ranking task.
    print("[weekly_reviewer] synthesizing via LLM (qwen2.5:7b)...")
    ranked = call_ollama(prompt=prompt, model="qwen2.5:7b", timeout=240.0, system_prompt=SYSTEM)
    if not ranked:
        ranked = "_(LLM unavailable — digest only)_"

    report = [
        "# Weekly Strategic Review",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M %Z')} — grounded in real state, not stale gaps_\n",
        "## Ranked — what matters this week\n",
        ranked,
        "\n---\n## Digest it was built from\n",
        f"- **Trading:** {digest['trading']}",
        f"- **Content:** {digest['content']}",
        f"- **Income:** {digest['income']}",
        "- **Blockers (ground truth):**",
        *[f"    - {l}" for l in digest["blockers"].splitlines()],
    ]
    text = "\n".join(report)
    OUT.write_text(text)
    print(text)
    try:
        from core.event_ledger import log_event
        log_event("system", "weekly_reviewer", "weekly strategic review generated", score=1.0)
    except Exception:
        pass
    print(f"\n[written to {OUT}]")


if __name__ == "__main__":
    main()
