"""Build dist/modules/chart-input-coverage.json.

JEG-314: enumerate every input file the trade-values chart reads, with a
honest "is there an automated freshness check?" flag. The dashboard surfaces
the full list so gaps in monitoring are visible.

JEG-317: extend with a single aggregate row for the actuals_*.json inputs,
plus the `mtime` field the dashboard reads to render age bands (amber when
the most recent file is older than 7 days, red when older than 14 days).

Schema
------
{
  "generated_at": "<iso8601>",
  "items": [
    {"name": "<path>",
     "freshness_source": "<human-readable source>",
     "monitor_check": <bool>,
     "last_checked": "<iso8601 or null>",
     "mtime": "<iso8601 or null>"}   # present only on the actuals aggregate
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


def _now_epoch() -> float:
    """UTC unix epoch seconds, used for age math."""
    return _dt.datetime.now(_dt.timezone.utc).timestamp()


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


def _players_freshness() -> str | None:
    """Read players.json meta.as_of (best-effort)."""
    players = _load_json(_resolve("data/fixtures/current/players.json"))
    if not players:
        return None
    meta = players.get("meta", {}) or {}
    return meta.get("as_of")


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

    players_as_of = _players_freshness()
    players_freshness = players_as_of if players_as_of else "?"
    if players_as_of:
        players_summary = f"meta.as_of={players_as_of}"
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

    # 2. data/fixtures/current/players.json — meta.as_of, monitored.
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

    # 5. data/fixtures/current/actuals_*.json — aggregate freshness.
    # JEG-317 collapses the per-file rows into one row carrying the mtime of
    # the most recent file; the dashboard renders age bands from this mtime
    # (amber > 7d, red > 14d). Monitored = True: this builder is the gate.
    actuals_pattern = _resolve("data/fixtures/current/actuals_*.json")
    actuals_files = sorted(glob.glob(actuals_pattern))
    if actuals_files:
        newest_path = max(actuals_files, key=os.path.getmtime)
        newest_mtime_ts = os.path.getmtime(newest_path)
        newest_mtime_iso = _dt.datetime.fromtimestamp(
            newest_mtime_ts, tz=_dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        newest_rel = os.path.relpath(newest_path, REPO_ROOT)
        age_days = int((_now_epoch() - newest_mtime_ts) // 86400)
        band = "red" if age_days > 14 else ("amber" if age_days > 7 else "ok")
        items.append({
            "name": "data/fixtures/current/actuals_*.json",
            "freshness_source": (
                f"mtime of most recent actuals_*.json (newest = {newest_rel}, "
                f"mtime={newest_mtime_iso}; age {age_days}d, band={band}); "
                "dashboard paints amber when >7d, red when >14d"
            ),
            "monitor_check": True,
            "last_checked": now,
            "mtime": newest_mtime_iso,
        })
    else:
        # No actuals files present — still list the row so the gap is visible
        # in the dashboard. mtime is null; the dashboard paints red unconditionally
        # when there's no file to check.
        items.append({
            "name": "data/fixtures/current/actuals_*.json",
            "freshness_source": (
                "no actuals_*.json files present on this checkout; "
                "ECR leg cannot subtract any YTD actuals"
            ),
            "monitor_check": True,
            "last_checked": now,
            "mtime": None,
        })

    # 6. app/trade-value-chart/assets/reference-freshness.json — self-reference (the report itself).
    items.append({
        "name": "app/trade-value-chart/assets/reference-freshness.json",
        "freshness_source": "self (this coverage is derived from it; freshness = its own generated_at)",
        "monitor_check": True,
        "last_checked": rf_generated,
    })

    # 7. app/trade-value-chart/assets/espn_inputs*.json — no file on this checkout.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build chart-input-coverage.json")
    parser.add_argument(
        "--output",
        default=os.path.join(REPO_ROOT, "dist/modules/chart-input-coverage.json"),
        help="Path to write the coverage JSON (default: dist/modules/chart-input-coverage.json)",
    )
    args = parser.parse_args(argv)

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