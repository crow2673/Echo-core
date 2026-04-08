import os
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from storage import LocalStore
from plaid_client import build_plaid_client
from crow_sync import CrowSyncEngine
from account_autofill import materialize_from_snapshot, build_series_payload
from savings_bridge import append_savings_to_history
from finance_engine import run_engine

load_dotenv()

app = Flask(__name__)
CORS(app)

store = LocalStore(Path(os.getenv("CROW_DATA_DIR", "./data")))
plaid_client = build_plaid_client()
sync_engine = CrowSyncEngine(store, plaid_client)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/api/plaid/create_link_token", methods=["POST"])
def create_link_token():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id", "default-user")
    client_name = payload.get("client_name", "Crow's Echo")
    products = payload.get("products", ["transactions"])

    link_token = sync_engine.create_link_token(
        user_id=user_id,
        client_name=client_name,
        products=products,
    )
    return jsonify({"link_token": link_token})


@app.route("/api/plaid/exchange_public_token", methods=["POST"])
def exchange_public_token():
    payload = request.get_json(silent=True) or {}
    public_token = payload.get("public_token")
    metadata = payload.get("metadata", {})

    if not public_token:
        return jsonify({"error": "Missing public_token"}), 400

    token_data = sync_engine.exchange_public_token(public_token, metadata)
    return jsonify(token_data)


@app.route("/api/plaid/sync", methods=["POST"])
def sync_plaid():
    payload = request.get_json(silent=True) or {}
    days = int(payload.get("days", 30))
    result = sync_engine.sync(days=days)
    return jsonify(result)


@app.route("/api/crow_snapshot", methods=["GET"])
def get_snapshot():
    return jsonify(store.read_snapshot())


@app.route("/api/materialize_accounts", methods=["POST"])
def materialize_accounts():
    return jsonify(materialize_from_snapshot())


@app.route("/api/account_graph_series", methods=["GET"])
def account_graph_series():
    return jsonify(build_series_payload())


@app.route("/api/push_savings_to_graph", methods=["POST"])
def push_savings_to_graph():
    return jsonify(append_savings_to_history())


@app.route("/api/engine", methods=["GET"])
def engine():
    result = run_engine("./data/transactions.csv")
    return jsonify(result)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    app.run(host=host, port=port, debug=True)
