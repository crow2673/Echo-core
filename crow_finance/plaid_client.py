import os

from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient


def build_plaid_client():
    plaid_env = os.getenv("PLAID_ENV", "sandbox").strip().lower()
    client_id = os.getenv("PLAID_CLIENT_ID", "").strip()
    secret = os.getenv("PLAID_SECRET", "").strip()

    host = {
        "sandbox": "https://sandbox.plaid.com",
        "production": "https://production.plaid.com",
    }.get(plaid_env, "https://sandbox.plaid.com")

    configuration = Configuration(
        host=host,
        api_key={
            "clientId": client_id,
            "secret": secret,
        },
    )

    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)
