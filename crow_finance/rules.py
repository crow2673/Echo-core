from collections import Counter


def categorize_transaction(desc, amount, tx_type, plaid_category=None):
    name = (desc or "").lower().strip()

    if tx_type == "income":
        if "onlineacct" in name or "deposit" in name or "credit interest" in name:
            return "income"
        return "income"

    checks = {
        "groceries": [
            "wm supercenter", "walmart", "aldi", "reasor", "grocery", "market"
        ],
        "food": [
            "mcdonald", "burger", "pizza", "restaurant", "doordash", "taco", "sonic"
        ],
        "fuel": [
            "shell", "quiktrip", "qt", "exxon", "fuel", "phillips", "gas station"
        ],
        "utilities": [
            "electric", "utility", "water", "internet", "gas bill", "phone bill"
        ],
        "insurance": [
            "insurance", "geico", "state farm", "progressive"
        ],
        "loan": [
            "transfer to loan account", "loan payment", "loan acct", "affirm"
        ],
        "housing": [
            "rent", "mortgage", "landlord"
        ],
        "subscriptions": [
            "netflix", "spotify", "prime", "hulu", "apple.com/bill"
        ],
        "travel": [
            "queen wilhelmina", "hotel", "inn", "lodge", "park", "state park"
        ],
        "transfers": [
            "transfer", "xfer", "cash app", "venmo", "zelle"
        ],
        "fees": [
            "fee", "bank fee", "overdraft"
        ],
    }

    for label, needles in checks.items():
        if any(n in name for n in needles):
            return label

    if plaid_category and isinstance(plaid_category, dict):
        primary = (plaid_category.get("primary") or "").lower()
        detailed = (plaid_category.get("detailed") or "").lower()
        joined = f"{primary} {detailed}"

        if "grocer" in joined:
            return "groceries"
        if "restaurant" in joined or "food" in joined:
            return "food"
        if "transport" in joined or "fuel" in joined:
            return "fuel"
        if "loan" in joined:
            return "loan"
        if "insurance" in joined:
            return "insurance"
        if "utility" in joined:
            return "utilities"
        if "subscription" in joined:
            return "subscriptions"
        if "travel" in joined or "hotel" in joined:
            return "travel"
        if "fee" in joined:
            return "fees"

    return "misc"


def detect_spending_leaks(transactions):
    leaks = {}

    for t in transactions:
        if t.get("type") != "expense":
            continue
        cat = t.get("cat", "misc")
        leaks[cat] = leaks.get(cat, 0) + float(t.get("amt", 0) or 0)

    return sorted(leaks.items(), key=lambda x: x[1], reverse=True)[:5]


def detect_recurring_bills(transactions):
    counts = Counter()
    totals = {}

    for t in transactions:
        if t.get("type") != "expense":
            continue

        cat = t.get("cat", "")
        if cat not in {"housing", "utilities", "insurance", "loan", "subscriptions"}:
            continue

        desc = (t.get("desc") or "").strip().lower()
        if not desc:
            continue

        key = (cat, desc[:40])
        counts[key] += 1
        totals[key] = totals.get(key, 0) + float(t.get("amt", 0) or 0)

    recurring = []
    for key, count in counts.items():
        if count >= 2:
            cat, desc = key
            recurring.append({
                "category": cat,
                "description": desc,
                "count": count,
                "total": round(totals[key], 2),
                "average": round(totals[key] / count, 2),
            })

    recurring.sort(key=lambda x: x["average"], reverse=True)
    return recurring


def classify_mode(snapshot):
    available = float(snapshot.get("available_cash", 0) or 0)
    income = float(snapshot.get("income_30d", 0) or 0)
    expenses = float(snapshot.get("expenses_30d", 0) or 0)
    monthly_net = income - expenses

    if available <= 100 or monthly_net < -250:
        return "Survival"
    if available <= 500 or monthly_net < 0:
        return "Stabilize"
    if income == 0 and expenses > 0:
        return "Risk-Off"
    return "Growth"


def build_recommendation(snapshot, mode):
    leaks = snapshot.get("leaks", [])
    recurring = snapshot.get("recurring_bills", [])
    available = float(snapshot.get("available_cash", 0) or 0)
    income = float(snapshot.get("income_30d", 0) or 0)
    expenses = float(snapshot.get("expenses_30d", 0) or 0)
    monthly_net = income - expenses

    top_leak = leaks[0] if leaks else None

    if mode == "Survival":
        if top_leak:
            return (
                f"Enter protection mode: cover overdue or near-term bills first, "
                f"and freeze non-essential spending until at least ${max(50, round(min(available, 50), 2)):.2f} is accounted for."
            )
        return "Enter protection mode. Cover essentials first and pause non-essential spending."

    if mode == "Stabilize":
        if top_leak:
            return (
                f"Stabilize cash flow. Your top variable spend is '{top_leak[0]}' at "
                f"${round(top_leak[1], 2)}. Trim that first and protect your buffer."
            )
        return "Stabilize cash flow. Trim variable spending and rebuild buffer."

    if mode == "Risk-Off":
        return "No reliable income trend yet. Stay read-only, track closely, and avoid risky moves."

    if top_leak:
        return (
            f"You are in growth mode. Keep bills current, preserve your base buffer, "
            f"and direct surplus toward the highest-yield or highest-priority goal."
        )

    return "Growth mode. Preserve your base and route surplus intentionally."
