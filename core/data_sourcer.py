#!/usr/bin/env python3
"""Import a leakage-controlled public calibration benchmark from Manifold."""
import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.prediction_ledger import calibration_stats, import_resolved_prediction

API = "https://api.manifold.markets/v0"
SOURCE = "manifold"
DEFAULT_SCOPE = "public.manifold.binary_balanced_24h"


def _get(path: str, params: dict) -> list[dict]:
    url = f"{API}/{path}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "Echo-calibration-sourcer/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _iso(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def _historical_snapshot(market: dict, horizon_hours: int) -> dict | None:
    resolution_time = market.get("resolutionTime")
    if not resolution_time:
        return None
    cutoff = resolution_time - horizon_hours * 60 * 60 * 1000
    bets = _get("bets", {"contractId": market["id"], "limit": 1000})
    eligible = [
        bet for bet in bets
        if bet.get("isFilled")
        and not bet.get("isCancelled")
        and bet.get("createdTime", resolution_time) <= cutoff
        and isinstance(bet.get("probAfter"), (int, float))
    ]
    if not eligible:
        return None
    bet = max(eligible, key=lambda row: row["createdTime"])
    return {
        "probability": float(bet["probAfter"]),
        "created_at": _iso(bet["createdTime"]),
        "forecast_bet_id": bet.get("id") or bet.get("betId"),
        "cutoff": _iso(cutoff),
    }


def fetch_entries(
    target: int = 30,
    horizon_hours: int = 24,
    market_limit: int = 1000,
) -> list[dict]:
    """Return a deterministic class-balanced benchmark of resolved binary markets."""
    markets = _get("markets", {"limit": market_limit})
    candidates = [
        market for market in markets
        if market.get("outcomeType") == "BINARY"
        and market.get("isResolved")
        and market.get("resolution") in ("YES", "NO")
        and market.get("resolutionTime")
    ]
    candidates.sort(key=lambda row: row["resolutionTime"])

    per_class = target // 2
    selected: list[dict] = []
    counts = {0: 0, 1: 0}
    for market in candidates:
        outcome = 1 if market["resolution"] == "YES" else 0
        class_target = per_class + (target % 2 if outcome == 1 else 0)
        if counts[outcome] >= class_target:
            continue
        snapshot = _historical_snapshot(market, horizon_hours)
        if snapshot is None:
            continue
        selected.append({
            "market": market,
            "snapshot": snapshot,
            "outcome": outcome,
        })
        counts[outcome] += 1
        if len(selected) >= target:
            break
    selected.sort(key=lambda row: row["snapshot"]["created_at"])
    return selected


def import_entries(entries: list[dict], scope: str = DEFAULT_SCOPE, horizon_hours: int = 24) -> int:
    inserted = 0
    for entry in entries:
        market = entry["market"]
        snapshot = entry["snapshot"]
        source_url = market.get("url", f"https://manifold.markets/market/{market['id']}")
        prediction_id = import_resolved_prediction(
            claim=market["question"],
            probability=snapshot["probability"],
            category="public.manifold.binary",
            evidence=json.dumps({
                "source_url": source_url,
                "forecast_bet_id": snapshot["forecast_bet_id"],
                "minimum_pre_resolution_hours": horizon_hours,
                "cutoff": snapshot["cutoff"],
            }),
            created_at=snapshot["created_at"],
            outcome=bool(entry["outcome"]),
            outcome_evidence=json.dumps({
                "source_url": source_url,
                "resolution": market["resolution"],
                "resolution_time": _iso(market["resolutionTime"]),
            }),
            resolved_at=_iso(market["resolutionTime"]),
            dataset_scope=scope,
            source_name=SOURCE,
            source_id=market["id"],
        )
        inserted += prediction_id is not None
    return inserted


def run(target: int = 30, horizon_hours: int = 24, scope: str = DEFAULT_SCOPE) -> dict:
    entries = fetch_entries(target=target, horizon_hours=horizon_hours)
    if len(entries) < 20:
        raise RuntimeError(
            f"only found {len(entries)} eligible entries; at least 20 are required"
        )
    outcomes = [entry["outcome"] for entry in entries]
    if len(set(outcomes)) != 2:
        raise RuntimeError("public benchmark lacks both positive and negative outcomes")
    inserted = import_entries(entries, scope=scope, horizon_hours=horizon_hours)
    stats = calibration_stats(dataset_scope=scope)
    result = {
        "source": SOURCE,
        "dataset_scope": scope,
        "selection": "class-balanced resolved binary markets",
        "minimum_pre_resolution_hours": horizon_hours,
        "fetched": len(entries),
        "inserted": inserted,
        "positive_outcomes": sum(outcomes),
        "negative_outcomes": len(outcomes) - sum(outcomes),
        "calibration": stats,
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=30)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    args = parser.parse_args()
    run(args.target, args.horizon_hours, args.scope)
