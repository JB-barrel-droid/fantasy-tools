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
    return {
        "key": key,
        "label": label,
        "value": entry.get("content_vintage"),
        "status": status,
        "age_days": age_days,
        "max_age_days": max_age_days,
        "freshness_ok": freshness_ok,
        "enforced": key in enforced_keys,
        "changed_since_prior_report": True,
        "note": (
            f"L1 status={gate_status}; "
            f"last_successful_import={entry.get('last_successful_import') or 'unknown'}; "
            "content_vintage is source provenance, not pull time"
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


def build_report(
    fixtures: Path,
    output: Path,
    today: date,
    max_age_days: int = 2,
    enforced_keys: tuple[str, ...] = DEFAULT_ENFORCED_KEYS,
    import_health_path: Path | None = None,
) -> dict[str, Any]:
    players = load_json(fixtures / "players.json")
    comparison = load_json(fixtures / "comparison-sources-data.json")
    news = load_json(fixtures / "player-news.json")
    import_health_source = import_health_path or (fixtures / "source-import-health.json")
    import_health = load_json(import_health_source)
    previous = prior_items(output)

    player_meta = players.get("meta", {})
    news_meta = news.get("meta", {})
    enforced_set = set(enforced_keys)
    items = [
        make_item("players.as_of", "Players artifact as_of", player_meta.get("as_of"), today, previous, max_age_days, enforced_set),
        make_item("players.ecr_content_date", "Expert/ECR content date", player_meta.get("ecr_content_date"), today, previous, max_age_days, enforced_set),
        make_item("players.espn_snapshot", "ESPN projection snapshot", player_meta.get("espn_snapshot"), today, previous, max_age_days, enforced_set),
        make_item("players.pm_snapshot", "Prediction-market snapshot", player_meta.get("pm_snapshot"), today, previous, max_age_days, enforced_set),
        make_item("players.kdst_snapshot", "K/DST snapshot", player_meta.get("kdst_snapshot"), today, previous, max_age_days, enforced_set),
        make_item("comparison.built_at", "Comparison source artifact build time", comparison.get("built_at"), today, previous, max_age_days, enforced_set),
        make_item("news.generated_at", "Player-news artifact generation time", news_meta.get("generated_at"), today, previous, max_age_days, enforced_set),
        make_item("news.trade_values_published_at", "Trade-value publication timestamp", news_meta.get("trade_values_published_at"), today, previous, max_age_days, enforced_set),
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

    hashes = {
        name: sha256(fixtures / name)
        for name in ("players.json", "comparison-sources-data.json", "player-news.json", "source-import-health.json")
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
            "l1_unhealthy_count": len(l1_unhealthy),
            "unchanged_count": sum(1 for item in items if not item["changed_since_prior_report"]),
            "max_age_days": max_age_days,
            "enforced_keys": list(enforced_keys),
        },
        "source_validation": comparison.get("source_validation", {}),
        "artifact_hashes": hashes,
        "items": items,
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
