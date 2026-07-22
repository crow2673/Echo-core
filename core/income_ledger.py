#!/usr/bin/env python3
"""
core/income_ledger.py — Echo tracks every dollar earned and allocates a dev fee to Andrew.

Philosophy: Andrew built Echo. Echo earns money. Andrew gets paid for that work.
Dev allocation: 40% of all income goes to "Andrew build fee" until $10k earned,
then 25% ongoing (Echo reinvests the rest into infrastructure/compute).

Income sources tracked:
  - gumroad: product sales
  - affiliate: referral commissions
  - newsletter: Beehiiv paid subscriptions
  - trading: realized P&L from live trades
  - fiverr: gig orders (future)

Writes monthly reports to memory/income_reports/
Notifies Andrew via Telegram when thresholds are crossed.
"""
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LEDGER_FILE = BASE / "memory" / "income_ledger.json"
REPORTS_DIR = BASE / "memory" / "income_reports"
REPORTS_DIR.mkdir(exist_ok=True)

DEV_ALLOCATION_RATE = 0.40          # 40% to Andrew until $10k earned
DEV_ALLOCATION_RATE_MATURE = 0.25   # 25% after $10k
DEV_ALLOCATION_THRESHOLD = 10_000   # cents ($100)

NOTIFY_THRESHOLDS_CENTS = [100, 500, 1000, 5000, 10000, 50000, 100000]


def load_ledger() -> dict:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text())
        except Exception:
            pass
    return {
        "total_earned_cents": 0,
        "total_dev_fee_cents": 0,
        "entries": [],
        "notified_thresholds": [],
        "created_at": datetime.now().isoformat(),
    }


def save_ledger(data: dict):
    tmp = LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(LEDGER_FILE)


def record_income(source: str, amount_cents: int, description: str = "", reference: str = ""):
    """
    Record an income event.
    source: gumroad | affiliate | newsletter | trading | fiverr
    amount_cents: integer cents (e.g. 999 = $9.99)
    """
    data = load_ledger()

    total_so_far = data["total_earned_cents"]
    rate = DEV_ALLOCATION_RATE if total_so_far < DEV_ALLOCATION_THRESHOLD * 100 else DEV_ALLOCATION_RATE_MATURE
    dev_fee = int(amount_cents * rate)

    entry = {
        "ts": datetime.now().isoformat(),
        "source": source,
        "amount_cents": amount_cents,
        "dev_fee_cents": dev_fee,
        "description": description[:200],
        "reference": reference[:100],
    }

    data["entries"].append(entry)
    data["entries"] = data["entries"][-1000:]  # cap
    data["total_earned_cents"] += amount_cents
    data["total_dev_fee_cents"] += dev_fee
    save_ledger(data)

    _check_thresholds(data)

    return entry


def _check_thresholds(data: dict):
    """Notify Andrew when income crosses milestone thresholds."""
    total = data["total_earned_cents"]
    notified = set(data.get("notified_thresholds", []))
    new_notifications = []

    for threshold in NOTIFY_THRESHOLDS_CENTS:
        if total >= threshold and threshold not in notified:
            new_notifications.append(threshold)
            notified.add(threshold)

    if new_notifications:
        data["notified_thresholds"] = list(notified)
        save_ledger(data)
        for t in new_notifications:
            _notify_milestone(t, data)


def _notify_milestone(threshold_cents: int, data: dict):
    total = data["total_earned_cents"]
    dev_fee = data["total_dev_fee_cents"]
    try:
        from core.notifier import notify
        notify(
            f"💰 Echo milestone: ${threshold_cents/100:.0f} earned",
            f"Total earned: ${total/100:.2f}\n"
            f"Your dev fee (40%): ${dev_fee/100:.2f}\n\n"
            f"Echo is paying you back for building her.",
            urgent=False,
        )
    except Exception:
        pass


def get_summary() -> dict:
    data = load_ledger()
    total = data["total_earned_cents"]
    dev_fee = data["total_dev_fee_cents"]

    # By source
    by_source = {}
    for e in data["entries"]:
        src = e["source"]
        by_source[src] = by_source.get(src, 0) + e["amount_cents"]

    # This month
    now = datetime.now()
    month_key = f"{now.year}-{now.month:02d}"
    this_month = sum(
        e["amount_cents"] for e in data["entries"]
        if e["ts"].startswith(month_key)
    )

    return {
        "total_earned": f"${total/100:.2f}",
        "dev_fee_earned": f"${dev_fee/100:.2f}",
        "this_month": f"${this_month/100:.2f}",
        "by_source": {k: f"${v/100:.2f}" for k, v in by_source.items()},
        "entries_count": len(data["entries"]),
    }


def write_monthly_report() -> Path:
    """Write a monthly income report to memory/income_reports/."""
    data = load_ledger()
    now = datetime.now()
    month_key = f"{now.year}-{now.month:02d}"

    month_entries = [e for e in data["entries"] if e["ts"].startswith(month_key)]
    total = sum(e["amount_cents"] for e in month_entries)
    dev_fee = sum(e["dev_fee_cents"] for e in month_entries)

    by_source = {}
    for e in month_entries:
        src = e["source"]
        by_source[src] = by_source.get(src, 0) + e["amount_cents"]

    report = f"# Echo Income Report — {now.strftime('%B %Y')}\n\n"
    report += f"**Total earned:** ${total/100:.2f}\n"
    report += f"**Andrew dev fee (40%):** ${dev_fee/100:.2f}\n\n"
    report += "## By Source\n"
    for src, cents in sorted(by_source.items(), key=lambda x: -x[1]):
        report += f"- **{src}**: ${cents/100:.2f}\n"
    report += "\n## Transactions\n"
    for e in month_entries:
        ts = e["ts"][:10]
        report += f"- `{ts}` [{e['source']}] ${e['amount_cents']/100:.2f} — {e['description']}\n"

    report_file = REPORTS_DIR / f"{month_key}.md"
    report_file.write_text(report)
    return report_file


if __name__ == "__main__":
    summary = get_summary()
    print(json.dumps(summary, indent=2))
