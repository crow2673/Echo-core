#!/usr/bin/env python3
"""Generate asset reports for Andrew."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_database import AssetDatabase

REPORT_DIR = BASE / "reports/assets"


def generate_asset_report(asset_id: str | None = None) -> Path:
    db = AssetDatabase()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = asset_id or "all_assets"
    path = REPORT_DIR / f"{name}_{stamp}.md"

    assets = [db.get_asset(asset_id)] if asset_id else db.list_assets()
    assets = [asset for asset in assets if asset]
    lines = ["# Echo Asset Report", "", f"Generated: {datetime.now().isoformat()}", ""]
    for asset in assets:
        aid = asset["asset_id"]
        lines.extend([
            f"## {aid} — {asset['name']}",
            "",
            f"- Type: {asset['type']}",
            f"- Manufacturer: {asset.get('manufacturer') or ''}",
            f"- Model: {asset.get('model') or ''}",
            f"- Status: {asset.get('status') or ''}",
            "",
            "### Open Tasks",
        ])
        tasks = db.open_tasks(aid)
        if tasks:
            lines.extend(f"- [{t['priority']}] {t['task']} ({t['status']})" for t in tasks)
        else:
            lines.append("- None")
        lines.extend(["", "### Recent Observations"])
        observations = db.recent_observations(limit=10, asset_id=aid)
        if observations:
            lines.extend(
                f"- {o['timestamp']} [{o['source']}] {o['summary']}"
                for o in observations
            )
        else:
            lines.append("- None")
        lines.append("")

    path.write_text("\n".join(lines))
    return path


def generate_json_summary() -> dict:
    db = AssetDatabase()
    return {
        "generated_at": datetime.now().isoformat(),
        "summary": db.asset_summary(),
        "assets": db.list_assets(),
        "open_tasks": db.open_tasks(),
    }


if __name__ == "__main__":
    report = generate_asset_report()
    print(json.dumps({"report": str(report)}, indent=2))
