from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from rules import (
    categorize_transaction,
    classify_mode,
    build_recommendation,
    detect_spending_leaks,
    detect_recurring_bills,
)


class CrowSyncEngine:
    def __init__(self, store, plaid_client):
        self.store = store
        self.client = plaid_client

    def create_link_token(self, user_id: str, client_name: str, products: List[str]) -> str:
        request = LinkTokenCreateRequest(
            products=[Products(p) for p in products],
            client_name=client_name,
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
        )
        response = self.client.link_token_create(request)
        return response["link_token"]

    def exchange_public_token(self, public_token: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self.client.item_public_token_exchange(request)
        token_data = {
            "access_token": response["access_token"],
            "item_id": response["item_id"],
            "institution_name": (metadata or {}).get("institution", {}).get("name"),
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }
        self.store.write_tokens(token_data)
        return token_data

    def _fetch_accounts(self, access_token: str) -> List[Dict[str, Any]]:
        request = AccountsBalanceGetRequest(access_token=access_token)
        response = self.client.accounts_balance_get(request)
        accounts = []
        for acc in response["accounts"]:
            accounts.append({
                "account_id": acc["account_id"],
                "name": acc["name"],
                "official_name": acc.get("official_name"),
                "type": getattr(acc.get("type"), "value", acc.get("type")),
                "subtype": getattr(acc.get("subtype"), "value", acc.get("subtype")),
                "mask": acc.get("mask"),
                "available_balance": (acc.get("balances") or {}).get("available"),
                "current_balance": (acc.get("balances") or {}).get("current"),
                "iso_currency_code": (acc.get("balances") or {}).get("iso_currency_code"),
            })
        return accounts

    def _fetch_transactions_sync(self, access_token: str) -> List[Dict[str, Any]]:
        cursor: Optional[str] = None
        added: List[Dict[str, Any]] = []

        while True:
            if cursor:
                request = TransactionsSyncRequest(access_token=access_token, cursor=cursor)
            else:
                request = TransactionsSyncRequest(access_token=access_token)

            response = self.client.transactions_sync(request)

            if hasattr(response, "to_dict"):
                response = response.to_dict()

            added.extend(response.get("added", []))
            cursor = response.get("next_cursor")

            if not response.get("has_more", False):
                break

        return added

    def _normalize_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(tx.get("amount") or 0)
        tx_type = "expense"
        if amount < 0:
            tx_type = "income"

        desc = tx.get("merchant_name") or tx.get("name") or "Bank transaction"
        clean_amount = abs(amount)
        category = categorize_transaction(
            desc,
            clean_amount,
            tx_type,
            tx.get("personal_finance_category"),
        )

        tx_date = tx.get("date")
        if isinstance(tx_date, (datetime, date)):
            tx_date = tx_date.isoformat()

        return {
            "id": tx.get("transaction_id"),
            "date": tx_date,
            "desc": desc,
            "cat": category,
            "amt": round(clean_amount, 2),
            "type": tx_type,
            "src": "plaid",
            "pending": bool(tx.get("pending")),
        }

    def sync(self, days: int = 30) -> Dict[str, Any]:
        tokens = self.store.read_tokens()
        access_token = tokens.get("access_token")
        if not access_token:
            raise RuntimeError("No bank has been linked yet. Connect an account first.")

        # Balance product pending approval — skip for now, use transactions only
        accounts = []
        raw_transactions = self._fetch_transactions_sync(access_token)
        cutoff = datetime.now().date() - timedelta(days=days)
        normalized = []

        for tx in raw_transactions:
            tx_date = tx.get("date")

            if isinstance(tx_date, str):
                tx_date = datetime.fromisoformat(tx_date).date()
            elif isinstance(tx_date, datetime):
                tx_date = tx_date.date()

            if tx_date and tx_date >= cutoff:
                normalized.append(self._normalize_transaction(tx))

        meta = {
            "institution_name": tokens.get("institution_name"),
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "transaction_count": len(normalized),
            "days": days,
        }
        crow = self._build_crow_snapshot(accounts, normalized)
        snapshot = {
            "accounts": accounts,
            "transactions": normalized,
            "meta": meta,
            "crow": crow,
        }
        self.store.write_snapshot(snapshot)
        return snapshot

    def _build_crow_snapshot(self, accounts: List[Dict[str, Any]], transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        income = sum(t["amt"] for t in transactions if t["type"] == "income")
        expenses = sum(t["amt"] for t in transactions if t["type"] == "expense")

        available = 0.0
        for a in accounts:
            bal = a.get("available_balance")
            if bal is None:
                bal = a.get("current_balance")
            if bal is not None:
                available += float(bal)

        leaks = detect_spending_leaks(transactions)
        recurring = detect_recurring_bills(transactions)
        monthly_net = round(income - expenses, 2)

        daily_burn = expenses / 30 if expenses > 0 else 0
        runway_days = round(available / daily_burn) if daily_burn > 0 and available > 0 else 0

        top_leak_category = leaks[0][0] if leaks else "none"
        top_leak_amount = round(leaks[0][1], 2) if leaks else 0.0

        pressure = []
        if monthly_net < 0:
            pressure.append(f"This month is running ${abs(monthly_net):.2f} behind")
        if leaks:
            pressure.append(f"Top expense category: {top_leak_category} (${top_leak_amount:.2f})")
        if recurring:
            pressure.append(f"Recurring bills detected: {len(recurring)}")

        snapshot = {
            "income_30d": round(income, 2),
            "expenses_30d": round(expenses, 2),
            "available_cash": round(available, 2),
            "transaction_count": len(transactions),
            "monthly_net": monthly_net,
            "runway_days": runway_days,
            "leaks": leaks,
            "recurring_bills": recurring,
            "top_leak_category": top_leak_category,
            "top_leak_amount": top_leak_amount,
            "pressure": pressure,
            "savings_buffer": round(max(available, 0), 2),
        }

        mode = classify_mode(snapshot)
        recommendation = build_recommendation(snapshot, mode)

        return {
            **snapshot,
            "mode": mode,
            "recommendation": recommendation,
        }
