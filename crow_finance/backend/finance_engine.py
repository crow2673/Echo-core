from datetime import datetime, timedelta
from pathlib import Path
import csv


def load_transactions(path):
    rows = []
    path = Path(path)
    if not path.exists():
        return rows

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_date = row.get("date") or row.get("Date") or ""
            raw_amount = row.get("amount") or row.get("Amount") or "0"
            raw_desc = row.get("description") or row.get("desc") or row.get("Description") or ""

            try:
                tx_date = datetime.fromisoformat(raw_date.strip())
            except Exception:
                try:
                    tx_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d")
                except Exception:
                    try:
                        tx_date = datetime.strptime(raw_date.strip(), "%m/%d/%Y")
                    except Exception:
                        continue

            try:
                amount = float(str(raw_amount).replace("$", "").replace(",", "").strip())
            except Exception:
                amount = 0.0

            rows.append({
                "date": tx_date,
                "amount": amount,
                "description": raw_desc.strip(),
            })

    rows.sort(key=lambda x: x["date"])
    return rows


def calculate_balance_history(rows, starting_balance=0.0):
    balance = float(starting_balance)
    history = []

    for row in rows:
        balance += row["amount"]
        history.append({
            "date": row["date"].isoformat(),
            "balance": round(balance, 2),
        })

    return history


def detect_recurring(rows):
    grouped = {}

    for row in rows:
        desc = row["description"]
        grouped.setdefault(desc, []).append(row)

    recurring = []
    for desc, items in grouped.items():
        if len(items) < 3:
            continue

        intervals = []
        for i in range(1, len(items)):
            intervals.append((items[i]["date"] - items[i - 1]["date"]).days)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)
        variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)

        if variance <= 25:
            avg_amount = sum(x["amount"] for x in items) / len(items)
            recurring.append({
                "description": desc,
                "avg_amount": round(avg_amount, 2),
                "interval_days": max(1, int(round(avg_interval))),
            })

    return recurring


def project_future(current_balance, recurring, days=30):
    future = []
    balance = float(current_balance)
    today = datetime.now()

    for i in range(days):
        day = today + timedelta(days=i)

        for rec in recurring:
            if i != 0 and i % rec["interval_days"] == 0:
                balance += rec["avg_amount"]

        future.append({
            "date": day.isoformat(),
            "balance": round(balance, 2),
        })

    return future


def calculate_survival_days(current_balance, recurring):
    daily_burn = 0.0
    for rec in recurring:
        if rec["avg_amount"] < 0:
            daily_burn += abs(rec["avg_amount"]) / rec["interval_days"]

    if daily_burn <= 0:
        return 999

    return max(0, int(current_balance / daily_burn))


def run_engine(csv_path):
    rows = load_transactions(csv_path)
    history = calculate_balance_history(rows)

    current_balance = history[-1]["balance"] if history else 0.0
    recurring = detect_recurring(rows)
    future = project_future(current_balance, recurring, days=30)
    survival_days = calculate_survival_days(current_balance, recurring)

    return {
        "ok": True,
        "current_balance": current_balance,
        "survival_days": survival_days,
        "history": history,
        "future": future,
        "recurring": recurring,
        "transaction_count": len(rows),
    }
