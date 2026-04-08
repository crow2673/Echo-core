import csv
import json
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/home/andrew/Downloads/crows_echo_bank_starter/backend/data")
IMPORT_PATH = BASE / "import.csv"
TRANSACTIONS_PATH = BASE / "transactions.csv"
SNAPSHOT_PATH = BASE / "snapshot.json"
IMPORT_LOG_PATH = BASE / "import_log.json"


def pick(row, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name]).strip()
    return ""


def parse_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return value


def parse_amount(row: dict) -> float:
    amount = pick(row, "amount", "Amount")
    debit = pick(row, "debit", "Debit")
    credit = pick(row, "credit", "Credit")

    def clean(x: str) -> float:
        x = x.replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
        return float(x) if x else 0.0

    if amount:
        return clean(amount)
    if debit or credit:
        return clean(credit) - clean(debit)
    return 0.0


def categorize(desc: str, amount: float) -> str:
    d = desc.lower()
    if amount > 0:
        return "income"
    if any(x in d for x in ["walmart", "aldi", "kroger", "market"]):
        return "groceries"
    if any(x in d for x in ["mcdonald", "doordash", "restaurant", "burger", "pizza"]):
        return "food"
    if any(x in d for x in ["shell", "exxon", "qt", "quiktrip", "fuel", "gas"]):
        return "gas"
    if any(x in d for x in ["rent", "mortgage"]):
        return "housing"
    if any(x in d for x in ["netflix", "spotify", "hulu", "prime"]):
        return "subscriptions"
    if any(x in d for x in ["loan", "affirm", "payment", "credit card"]):
        return "loan"
    return "misc"


def main():
    if not IMPORT_PATH.exists():
        raise FileNotFoundError(f"Missing import file: {IMPORT_PATH}")

    with IMPORT_PATH.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    normalized = []
    for i, row in enumerate(rows, start=1):
        date = parse_date(pick(row, "date", "Date", "posted_date", "Posted Date", "transaction_date"))
        desc = pick(row, "description", "Description", "desc", "merchant", "Merchant", "name", "Name")
        amount = parse_amount(row)

        if not date or not desc:
            continue

        tx_type = "income" if amount > 0 else "expense"
        amt_abs = round(abs(amount), 2)

        normalized.append({
            "id": f"csv-{i}",
            "date": date,
            "desc": desc,
            "cat": categorize(desc, amount),
            "amt": amt_abs,
            "type": tx_type,
            "src": "csv_import",
            "pending": False,
        })

    normalized.sort(key=lambda x: x["date"])

    with TRANSACTIONS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "amount", "description"])
        writer.writeheader()
        for tx in normalized:
            signed_amount = tx["amt"] if tx["type"] == "income" else -tx["amt"]
            writer.writerow({
                "date": tx["date"],
                "amount": signed_amount,
                "description": tx["desc"],
            })

    income_30d = round(sum(t["amt"] for t in normalized if t["type"] == "income"), 2)
    expenses_30d = round(sum(t["amt"] for t in normalized if t["type"] == "expense"), 2)
    available_cash = round(income_30d - expenses_30d, 2)

    snapshot = {
        "accounts": [],
        "transactions": normalized,
        "meta": {
            "source": "csv_import",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "transaction_count": len(normalized),
        },
        "crow": {
            "income_30d": income_30d,
            "expenses_30d": expenses_30d,
            "available_cash": available_cash,
            "transaction_count": len(normalized),
        },
    }

    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    log_entry = {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(IMPORT_PATH),
        "transaction_count": len(normalized),
    }

    existing = []
    if IMPORT_LOG_PATH.exists():
        try:
            existing = json.loads(IMPORT_LOG_PATH.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    existing.append(log_entry)
    IMPORT_LOG_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(f"Imported {len(normalized)} transactions")
    print(f"Wrote: {TRANSACTIONS_PATH}")
    print(f"Wrote: {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
