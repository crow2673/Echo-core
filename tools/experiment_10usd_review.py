#!/usr/bin/env python3
"""tools/experiment_10usd_review.py — 24h review of the $10 experiment.

Reads the experiment state + baseline and prints a full review report:
  (1) final equity vs $10.00 start (P&L $ and %)
  (2) every closed trade (symbol/entry/exit/pl/reason)
  (3) the decision-log narrative of what the adaptive strategy did
  (4) diff against the captured baseline

If the experiment hasn't flattened yet, it flattens first so the review is final.
Writes the report to memory/experiment_10usd_review.md and prints to stdout.

Run any time: python3 tools/experiment_10usd_review.py
"""
import json, subprocess, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STATE = BASE / "memory/experiment_10usd_state.json"
BASELINE = BASE / "memory/experiment_baseline_10usd.json"
LOG = BASE / "logs/experiment_10usd.log"
OUT = BASE / "memory/experiment_10usd_review.md"
HARNESS = BASE / "core/experiment_10usd.py"


def load(p):
    return json.loads(p.read_text()) if p.exists() else None


def main():
    st = load(STATE)
    if not st:
        print("No experiment state found — nothing to review.")
        return

    # Ensure it's finalized: if still holding or not done, flatten.
    if st.get("status") != "done" or st.get("position"):
        print("Experiment not finalized — flattening before review...")
        try:
            subprocess.run([sys.executable, str(HARNESS), "--flatten"],
                           cwd=str(BASE), timeout=120, check=False)
        except Exception as e:
            print(f"(flatten attempt errored: {e})")
        st = load(STATE)

    start = st.get("start_budget", 10.0)
    trades = st.get("trades", [])
    # final equity = budget (flat) + any residual position mark (should be flat)
    final_eq = st.get("budget", start)
    pl = final_eq - start
    pl_pct = (pl / start * 100) if start else 0

    L = []
    L.append("# $10 / 24h Experiment — Review")
    L.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}_\n")
    L.append(f"- **Mode:** {st.get('mode')}")
    L.append(f"- **Started:** {st.get('started_at')}")
    L.append(f"- **Deadline:** {st.get('deadline')}")
    L.append(f"- **Status:** {st.get('status')}\n")

    # (1) result
    verdict = "✅ GAIN" if pl > 0 else ("🔻 LOSS" if pl < 0 else "➖ FLAT")
    L.append("## 1. Result")
    L.append(f"| Start | Final | P&L | Return |")
    L.append(f"|---|---|---|---|")
    L.append(f"| ${start:.2f} | ${final_eq:.2f} | **${pl:+.4f}** | **{pl_pct:+.2f}%** {verdict} |\n")
    L.append(f"- Realized P&L (sum of closed trades): ${st.get('realized_pl', 0):+.4f}")
    L.append(f"- Trades taken: {len(trades)}\n")

    # (2) trade ledger
    L.append("## 2. Trade-by-trade")
    if trades:
        L.append("| # | Symbol | Entry | Exit | Qty | P&L | Exit reason |")
        L.append("|---|---|---|---|---|---|---|")
        for i, t in enumerate(trades, 1):
            L.append(f"| {i} | {t['symbol']} | ${t['entry']:,.2f} | ${t['exit']:,.2f} | "
                     f"{t['qty']:.8f} | ${t['pl']:+.4f} | {t['reason']} |")
        wins = sum(1 for t in trades if t['pl'] > 0)
        L.append(f"\n- Win rate: {wins}/{len(trades)} "
                 f"({wins/len(trades)*100:.0f}%)")
    else:
        L.append("_No trades were closed — strategy never found a qualifying entry, "
                 "or held a single position to the deadline._")
    L.append("")

    # (3) decision narrative
    L.append("## 3. What the adaptive strategy did")
    decisions = st.get("log", [])
    key = [d for d in decisions if any(k in d["msg"] for k in
           ("ENTER", "EXIT", "FILLED", "DEADLINE", "DONE", "standing down", "FAILED"))]
    if key:
        for d in key:
            ts = d["ts"][11:19]
            L.append(f"- `{ts}` {d['msg']}")
    else:
        L.append("_(no decision events logged)_")
    L.append("")

    # (4) baseline diff
    L.append("## 4. Diff vs baseline")
    bl = load(BASELINE)
    if bl:
        L.append(f"- Baseline captured: {bl.get('captured_at_local','?')}")
        L.append(f"- Account-level baseline (the whole paper account at start): "
                 f"equity ${bl.get('equity')}, positions {[p['symbol'] for p in bl.get('positions',[])]}")
        L.append(f"- The experiment itself is isolated: it ran on its own ${start:.2f} budget, "
                 f"separate from the main portfolio.")
    else:
        L.append("_baseline file missing_")
    L.append("")

    report = "\n".join(L)
    OUT.write_text(report)
    print(report)
    print(f"\n[review written to {OUT}]")


if __name__ == "__main__":
    main()
