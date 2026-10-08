#!/usr/bin/env python3
"""Audit finished trade-value references for freshness without mutating data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "data" / "fixtures" / "current"
DEFAULT_OUTPUT = ROOT / "output" / "reference-freshness.json"
DEFAULT_ENFORCED_KEYS = ("comparison.built_at",)
# JEG-316: chart inputs are a small subset of freshness rows that feed the
# trade-value chart directly. Surfacing them with a stable age-band color
# lets the dashboard flag stale inputs even when the comparison artifact
# itself is current.
DEFAULT_CHART_INPUT_KEYS: tuple[str, ...] = (
    "players.as_of",
)


def color_for(age_days: int | None, max_age_days: int) -> str:
    """Map age (in days) to a dashboard age-band color.

    Bands, expressed against `max_age_days` (the existing freshness gate):
    - green:   age <= max_age_days        (within freshness window)
    - yellow:  max_age_days < age <= 2 * max_age_days  (warning band)
    - red:     age > 2 * max_age_days     (well past the window)
    - unknown: no observed date (e.g. "?")
    """
    if age_days is None:
        return "unknown"
    if age_days < 0:
        return "unknown"
    if age_days <= max_age_days:
        return "green"
    if age_days <= 2 * max_age_days:
        return "yellow"
    return "red"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
      for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def status_for(value: Any, today: date) -> str:
    observed = parse_date(value)
    if observed is None:
        return "unknown"
    if observed == today:
        return "same_day"
    if observed < today:
        return "stale"
    return "future_dated"


def prior_items(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    return {item["key"]: item for item in payload.get("items", []) if isinstance(item, dict) and item.get("key")}


def make_item(
    key: str,
    label: str,
    value: Any,
    today: date,
    prior: dict[str, dict[str, Any]],
    max_age_days: int,
    enforced_keys: set[str],
) -> dict[str, Any]:
    previous = prior.get(key, {})
    changed = previous.get("value") != value
    note = "changed" if changed else "unchanged"
    observed = parse_date(value)
    age_days = (today - observed).days if observed is not None else None
    status = status_for(value, today)
    freshness_ok = observed is not None and 0 <= age_days <= max_age_days
    return {
        "key": key,
        "label": label,
        "value": value,
        "status": status,
        "age_days": age_days,
        "max_age_days": max_age_days,
        "freshness_ok": freshness_ok,
        "color": color_for(age_days, max_age_days),
        "enforced": key in enforced_keys,
        "changed_since_prior_report": changed,
        "note": note,
    }


def make_import_item(
    key: str,
    label: str,
    entry: dict[str, Any],
    today: date,
    max_age_days: int,
    enforced_keys: set[str],
) -> dict[str, Any]:
    observed = parse_date(entry.get("last_successful_import"))
    age_days = (today - observed).days if observed is not None else None
    gate_status = entry.get("status") or "unknown"
    freshness_ok = gate_status == "ok" and observed is not None and 0 <= age_days <= max_age_days
    status = "same_day" if freshness_ok and age_days == 0 else ("stale" if not freshness_ok else "current")
    content_vintage = entry.get("content_vintage") or entry.get("vintage")
    return {
        "key": key,
        "label": label,
        "value": content_vintage,
        "status": status,
        "age_days": age_days,
        "max_age_days": max_age_days,
        "freshness_ok": freshness_ok,
        "color": color_for(age_days, max_age_days),
        "enforced": key in enforced_keys,
        "changed_since_prior_report": True,
        "note": (
            f"L1 status={gate_status}; "
            f"last_successful_import={entry.get('last_successful_import') or 'unknown'}; "
            f"content_vintage is {content_vintage} source provenance, not pull time"
        ),
        "l1_status": gate_status,
        "failure_reason": entry.get("failure_reason"),
    }


def _relative_to_root(path: Path) -> str:
    """Path as written in the repo, falling back to absolute when outside it."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# GAP-034 / GAP-FRESH-SAVED-VS-PUBLISHED (2026-10-08): comparison.built_at is
# the time ANY section was last promoted, so it says nothing about how old
# each source's values are. Each source gets its own row: the content week the
# page PUBLISHES (the fixture section, read as the page reads it) next to the
# newest week SAVED in Supabase (import health), against the current content
# week. One place, both views, named. Reported, never enforced: a lagging
# source is a warning (build-lag-001), not a deploy block.
COMPARISON_SOURCES = ("usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball")


def make_source_week_item(source: str, section: dict[str, Any] | None,
                          import_entry: dict[str, Any] | None, today: date) -> dict[str, Any]:
    import sys
    sys.path.insert(0, str(ROOT / "pipelines"))
    from nfl_week import content_week, section_content_week, week_of_date, week_of_label

    current = content_week(today)
    published = section_content_week(section) if section else None
    entry = import_entry or {}
    saved = entry.get("content_week") if isinstance(entry.get("content_week"), int) else None
    if saved is None:
        vintage = entry.get("content_vintage")
        saved = week_of_label(vintage) or week_of_date(vintage)
    behind = None if published is None else max(current - published, 0)
    if published is None:
        status, color = "unknown", "unknown"
    elif behind == 0:
        status, color = "current", "green"
    elif behind == 1:
        status, color = "one_week_behind", "yellow"
    else:
        status, color = "stale", "red"
    note = f"published Week {published}" if published else "published week unknown"
    note += f"; newest saved Week {saved}" if saved else "; saved week unknown"
    if published and saved and saved > published:
        note += " (saved but not yet published: the next bake promotes it)"
    elif published and saved and saved < published:
        note += " (the import-health report is older than the published fixture)"
    return {
        "key": f"comparison.source.{source}",
        "label": f"{source} content week (published / saved)",
        "value": f"Week {published}" if published else None,
        "published_week": published,
        "saved_week": saved,
        "current_content_week": current,
        "weeks_behind": behind,
        "pending_promotion": bool(published and saved and saved > published),
        "status": status,
        "color": color,
        "freshness_ok": behind is not None and behind <= 1,
        "enforced": False,
        "changed_since_prior_report": True,
        "note": note,
    }


def build_report(
    fixtures: Path,
    output: Path,
    today: date,
    max_age_days: int = 2,
    enforced_keys: tuple[str, ...] = DEFAULT_ENFORCED_KEYS,
    import_health_path: Path | None = None,
    chart_input_keys: tuple[str, ...] = DEFAULT_CHART_INPUT_KEYS,
) -> dict[str, Any]:
    players = load_json(fixtures / "players.json")
    comparison = load_json(fixtures / "comparison-sources-data.json")
    import_health_source = import_health_path or (fixtures / "source-import-health.json")
    import_health = load_json(import_health_source)
    previous = prior_items(output)

    player_meta = players.get("meta", {})
    enforced_set = set(enforced_keys)
    chart_input_set = set(chart_input_keys)
    items = [
        make_item("players.as_of", "Players artifact as_of", player_meta.get("as_of"), today, previous, max_age_days, enforced_set),
        make_item("players.espn_snapshot", "ESPN projection snapshot", player_meta.get("espn_snapshot"), today, previous, max_age_days, enforced_set),
        make_item("comparison.built_at", "Comparison fixture last rebuilt (any source promotion; not input freshness)", comparison.get("built_at"), today, previous, max_age_days, enforced_set),
    ]
    if import_health.get("schema") == "trade-value-import-health-v1":
        items.append(
            make_item(
                "source_import.checked_at",
                "L1 import health checked_at",
                import_health.get("checked_at"),
                today,
                previous,
                max_age_days,
                enforced_set,
            )
        )
        for source, entry in sorted((import_health.get("sources") or {}).items()):
            if isinstance(entry, dict):
                items.append(
                    make_import_item(
                        f"source_import.{source}",
                        f"L1 {source} content vintage",
                        entry,
                        today,
                        max_age_days,
                        enforced_set,
                    )
                )

    sections = comparison.get("sources") or {}
    import_sources = import_health.get("sources") or {} if import_health.get("schema") == "trade-value-import-health-v1" else {}
    source_weeks = [make_source_week_item(source, sections.get(source), import_sources.get(source), today)
                    for source in COMPARISON_SOURCES if source in sections]

    hashes = {
        name: sha256(fixtures / name)
        for name in ("players.json", "comparison-sources-data.json", "source-import-health.json")
    }
    all_same_day = all(item["status"] == "same_day" for item in items if item["status"] != "unknown")
    stale = [item for item in items if item["status"] == "stale"]
    unknown = [item for item in items if item["status"] == "unknown"]
    expired = [item for item in items if not item["freshness_ok"]]
    enforced_expired = [item for item in items if item["enforced"] and not item["freshness_ok"]]
    l1_unhealthy = [
        item for item in items
        if item["key"].startswith("source_import.")
        and item["key"] != "source_import.checked_at"
        and not item["freshness_ok"]
    ]
    # The per-source week rows are reported beside the dated items but kept
    # out of the legacy day-age counts above (different unit: weeks).
    items.extend(source_weeks)
    # JEG-316: chart inputs are a small subset of freshness rows that feed the
    # trade-value chart directly. Surface them as a dedicated section so the
    # dashboard can flag stale inputs even when the comparison artifact is
    # current. Order is the brief's order, falling back to discovery order.
    chart_inputs: list[dict[str, Any]] = []
    seen_chart_keys: set[str] = set()
    for key in chart_input_keys:
        for item in items:
            if item["key"] == key and key not in seen_chart_keys:
                chart_inputs.append({**item, "chart_input": True})
                seen_chart_keys.add(key)
                break
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        # Repo-relative. This shipped as an absolute path, so the artifact
        # committed into app/ and dist/ carried whichever machine last ran
        # sync (e.g. /home/hatch/workspace/...) and churned on every run.
        "fixture_dir": _relative_to_root(fixtures),
        "import_health_source": _relative_to_root(import_health_source),
        "summary": {
            "all_known_dates_same_day": all_same_day,
            "stale_count": len(stale),
            "unknown_count": len(unknown),
            "expired_count": len(expired),
            "enforced_expired_count": len(enforced_expired),
            # GAP-033: the keys past the freshness window, so the status page
            # (modules/surfaces.json warn_path) shows each one as a warning.
            "expired_keys": [item["key"] for item in expired],
            "l1_unhealthy_count": len(l1_unhealthy),
            "unchanged_count": sum(1 for item in items if not item["changed_since_prior_report"]),
            "max_age_days": max_age_days,
            "enforced_keys": list(enforced_keys),
            # JEG-316: chart-input rollup so the dashboard summary tile can
            # render a count without re-scanning the chart_inputs list.
            "chart_input_count": len(chart_inputs),
            "chart_input_at_risk_count": sum(
                1 for item in chart_inputs if item["color"] in ("yellow", "red")
            ),
            "chart_input_keys": list(chart_input_keys),
            # The honest comparison summary: built_at is only when the fixture
            # was last rebuilt; the oldest PUBLISHED source week is what the
            # page's values actually are.
            "comparison_built_at": comparison.get("built_at"),
            "comparison_oldest_published_week": min(
                (i["published_week"] for i in source_weeks if i["published_week"]), default=None),
            "comparison_sources_behind": sorted(
                i["key"].rsplit(".", 1)[1] for i in source_weeks if (i["weeks_behind"] or 0) > 0),
            "comparison_sources_pending_promotion": sorted(
                i["key"].rsplit(".", 1)[1] for i in source_weeks if i["pending_promotion"]),
        },
        "source_validation": comparison.get("source_validation", {}),
        "artifact_hashes": hashes,
        "items": items,
        # JEG-316: dedicated section listing only the chart-feeding inputs.
        # Each row carries the same shape as `items` plus `chart_input: true`
        # and an age-band `color` (green/yellow/red/unknown).
        "chart_inputs": chart_inputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--max-age-days", type=int, default=2)
    parser.add_argument("--enforce-key", action="append", dest="enforce_keys")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    today = date.fromisoformat(args.today)
    enforce_keys = tuple(args.enforce_keys or DEFAULT_ENFORCED_KEYS)
    report = build_report(args.fixtures, args.output, today, args.max_age_days, enforce_keys)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.output}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    if args.enforce:
        expired = [item for item in report["items"] if item["enforced"] and not item["freshness_ok"]]
        if expired:
            print("Freshness gate failed:")
            for item in expired:
                print(
                    f"- {item['label']}: {item.get('value')!r} "
                    f"(age_days={item.get('age_days')}, max_age_days={item['max_age_days']})"
                )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
