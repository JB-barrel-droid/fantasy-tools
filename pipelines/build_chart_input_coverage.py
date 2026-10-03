"""Build dist/modules/chart-input-coverage.json.

JEG-314: enumerate every input file the trade-values chart reads, with a
honest "is there an automated freshness check?" flag. The dashboard surfaces
the full list so gaps in monitoring are visible.

JEG-317 will extend this with live, validated row counts and puller timestamps.
This first pass keeps the schema deliberately small: name, freshness_source,
monitor_check, last_checked.

Schema
------
{
  "generated_at": "<iso8601>",
  "items": [
    {"name": "<path>",
     "freshness_source": "<human-readable source>",
     "monitor_check": <bool>,
     "last_checked": "<iso8601 or null>"}
  ]
}

The monitor_check flag is the contract: True means an automated gate reports
freshness for this input somewhere (reference-freshness.json,
source-import-health.json, etc.); False means the input is consumed but
NOT covered by any monitor — visible as a gap, not hidden.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
from typing import Any


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _now_utc() -> str:
    """ISO 8601 UTC timestamp, second precision."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _resolve(rel_path: str) -> str:
    return os.path.join(REPO_ROOT, rel_path)


def _fixture_exists(rel_path: str) -> bool:
    return os.path.isfile(_resolve(rel_path))


def _players_freshness() -> tuple[str | None, str | None]:
    """Read players.json meta.as_of and meta.kdst_snapshot (best-effort)."""
    players = _load_json(_resolve("data/fixtures/current/players.json"))
    if not players:
        return None, None
    meta = players.get("meta", {}) or {}
    return meta.get("as_of"), meta.get("kdst_snapshot")


def _reference_freshness_lookup() -> dict[str, str]:
    """Map from input name -> freshness value parsed out of reference-freshness.json."""
    rf = _load_json(_resolve("app/trade-value-chart/assets/reference-freshness.json"))
    if not rf:
        return {}
    out: dict[str, str] = {}
    items = rf.get("items", []) or []
    by_key = {it.get("key"): it for it in items if isinstance(it, dict)}

    # comparison-sources-data.json -> "comparison.built_at"
    cmp_item = by_key.get("comparison.built_at")
    if cmp_item:
        out["data/fixtures/current/comparison-sources-data.json"] = str(cmp_item.get("value", ""))

    # player-news.json -> "news.generated_at"
    news_item = by_key.get("news.generated_at")
    if news_item:
        out["data/fixtures/current/player-news.json"] = str(news_item.get("value", ""))

    # players.json -> "players.as_of"
    as_of_item = by_key.get("players.as_of")
    if as_of_item:
        out["data/fixtures/current/players.json"] = str(as_of_item.get("value", ""))

    return out


def build_items(now: str) -> list[dict[str]]:
    """Assemble the coverage rows.

    `monitor_check` is the audited claim about whether *any* automated check
    in this repo reports on this input's freshness. False is a real gap,
    not a TODO to silence.
    """
    items: list[dict[str]] = []

    rf = _load_json(_resolve("app/trade-value-chart/assets/reference-freshness.json"))
    rf_generated = rf.get("generated_at") if rf else None
    rf_lookup = _reference_freshness_lookup()

    players_as_of, players_kdst = _players_freshness()
    players_freshness = players_as_of if players_as_of else "?"
    if players_as_of:
        players_summary = f"meta.as_of={players_as_of}"
        if players_kdst and players_kdst != "?":
            players_summary += f"; meta.kdst_snapshot={players_kdst}"
        elif players_kdst == "?":
            players_summary += "; meta.kdst_snapshot=unknown"
    else:
        players_summary = "meta.as_of unavailable"

    # 1. data/fixtures/current/comparison-sources-data.json — monitored.
    items.append({
        "name": "data/fixtures/current/comparison-sources-data.json",
        "freshness_source": (
            "reference-freshness.json items[comparison.built_at]"
            f" (value={rf_lookup.get('data/fixtures/current/comparison-sources-data.json', '?')}; "
            f"report generated {rf_generated or 'unavailable'})"
        ),
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 2. data/fixtures/current/players.json — meta.as_of + meta.kdst_snapshot, monitored.
    items.append({
        "name": "data/fixtures/current/players.json",
        "freshness_source": players_summary,
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 3. data/fixtures/current/players.naming-manifest.json — manifest pin, NOT separately monitored.
    items.append({
        "name": "data/fixtures/current/players.naming-manifest.json",
        "freshness_source": "manifest of public.players identity projection; re-pinned with players.json (no separate monitor)",
        "monitor_check": False,
        "last_checked": rf_generated,
    })

    # 4. app/trade-value-chart/assets/adjustment-inputs.json — monitored.
    items.append({
        "name": "app/trade-value-chart/assets/adjustment-inputs.json",
        "freshness_source": "reference-freshness.json (fit.combo_note / fixture_built_at branch)",
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 5. data/fixtures/current/actuals_*.json — consumed by ECR leg, NOT monitored.
    actuals_pattern = _resolve("data/fixtures/current/actuals_*.json")
    actuals_files = sorted(glob.glob(actuals_pattern))
    for path in actuals_files:
        rel = os.path.relpath(path, REPO_ROOT)
        items.append({
            "name": rel,
            "freshness_source": "YTD actuals subtracted from ECR leg (288 players); no freshness monitor",
            "monitor_check": False,
            "last_checked": None,
        })

    # 6. data/fixtures/current/player-news.json — monitored via reference-freshness.
    items.append({
        "name": "data/fixtures/current/player-news.json",
        "freshness_source": (
            "reference-freshness.json items[news.generated_at]"
            f" (value={rf_lookup.get('data/fixtures/current/player-news.json', '?')}; "
            f"report generated {rf_generated or 'unavailable'})"
        ),
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 7. app/trade-value-chart/assets/reference-freshness.json — self-reference (the report itself).
    items.append({
        "name": "app/trade-value-chart/assets/reference-freshness.json",
        "freshness_source": "self (this coverage is derived from it; freshness = its own generated_at)",
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 8. app/trade-value-chart/assets/espn_inputs*.json — no file on this checkout.
    espn_inputs_glob = sorted(glob.glob(_resolve("app/trade-value-chart/assets/espn_inputs*.json")))
    if espn_inputs_glob:
        for path in espn_inputs_glob:
            rel = os.path.relpath(path, REPO_ROOT)
            items.append({
                "name": rel,
                "freshness_source": "ESPN intake inputs (DDF two-tier leg); no dedicated monitor",
                "monitor_check": False,
                "last_checked": None,
            })
    else:
        # No file present — still list it so the gap is visible in the dashboard.
        items.append({
            "name": "app/trade-value-chart/assets/espn_inputs*.json",
            "freshness_source": "ESPN intake inputs (DDF two-tier leg); file not present on this checkout",
            "monitor_check": False,
            "last_checked": None,
        })

    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Build chart-input-coverage.json")
    parser.add_argument(
        "--output",
        default=os.path.join(REPO_ROOT, "dist/modules/chart-input-coverage.json"),
        help="Path to write the coverage JSON (default: dist/modules/chart-input-coverage.json)",
    )
    args = parser.parse_args()

    now = _now_utc()
    payload = {
        "generated_at": now,
        "items": build_items(now),
    }

    out_path = args.output
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    monitored = sum(1 for it in payload["items"] if it["monitor_check"])
    unmonitored = len(payload["items"]) - monitored
    print(f"wrote {out_path}: {len(payload['items'])} inputs "
          f"({monitored} monitored, {unmonitored} unmonitored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())