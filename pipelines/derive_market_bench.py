#!/usr/bin/env python3
"""Derive market-bench backups-per-starter ratios from FFC ADP snapshots (JEG-558).

Source: Fantasy Football Calculator 12-team PPR ADP archive HTML pages (human
picks, 15-round drafts with K and DEF). The JSON API and /adp/csv are
robots-disallowed and are not used.

  python3 pipelines/derive_market_bench.py --fetch    # save HTML tables -> snapshots
  python3 pipelines/derive_market_bench.py --derive   # print derived ratios (no write)

config/market_bench.json holds the FROZEN published ratios (Jeremy, 2026-10-10);
this script is a one-off reproduction check, not a scheduled job. Fails closed
when a table lists fewer players than 12 x rounds x 0.9 (truncated page).
"""
import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "inputs" / "market_bench"
TEAMS, ROUNDS, MIN_FRAC = 12, 15, 0.9
FORMATS = {
    "one_qb": {"years": [2016, 2018, 2020, 2024], "path": "ppr",
               "starters": {"QB": 1, "RB": 2.5, "WR": 2.5, "TE": 1, "K": 1, "DEF": 1}},
    "two_qb": {"years": [2018, 2020, 2022, 2024], "path": "2qb",
               "starters": {"QB": 2, "RB": 2.5, "WR": 2.5, "TE": 1, "K": 1, "DEF": 1}},
}
EXCLUDED_SNAPSHOTS = {"one_qb": [2022]}  # saved for the record; table truncated
POS_MAP = {"PK": "K"}
ROW_RE = re.compile(r"<tr class='(\w+)'>(.*?)</tr>", re.S)


def url(fmt, year):
    return f"https://fantasyfootballcalculator.com/adp/{FORMATS[fmt]['path']}/12-team/all/{year}"


def parse_html(html):
    rows = []
    for _cls, body in ROW_RE.findall(html):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)]
        if len(cells) < 9:
            continue
        pos = POS_MAP.get(cells[2], cells[2])
        rows.append({"rank": int(cells[0]), "name": cells[1], "pos": pos, "team": cells[3],
                     "adp": float(cells[4]), "times_drafted": int(cells[8].replace(",", ""))})
    return rows


def snap_path(fmt, year):
    return SNAP_DIR / f"ffc_adp_{fmt}_{year}.json"


def fetch():
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for fmt, spec in FORMATS.items():
        for year in spec["years"] + EXCLUDED_SNAPSHOTS.get(fmt, []):
            req = urllib.request.Request(url(fmt, year), headers={"User-Agent": "fantasy-tools-bench-snapshot"})
            rows = parse_html(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            snap_path(fmt, year).write_text(json.dumps(
                {"source_url": url(fmt, year), "rows": rows}, indent=1) + "\n")
            print(fmt, year, len(rows))


def year_shares(rows, fmt, year):
    if len(rows) < TEAMS * ROUNDS * MIN_FRAC:
        raise ValueError(f"{fmt} {year}: {len(rows)} listed players < {TEAMS * ROUNDS * MIN_FRAC:.0f} (truncated table)")
    counts = Counter(r["pos"] for r in rows)
    return {pos: counts[pos] / len(rows) * ROUNDS for pos in FORMATS[fmt]["starters"]}


def derive(fmt):
    spec = FORMATS[fmt]
    shares = [year_shares(json.loads(snap_path(fmt, y).read_text())["rows"], fmt, y) for y in spec["years"]]
    out = {}
    for pos, starters in spec["starters"].items():
        rostered = sum(s[pos] for s in shares) / len(shares)
        out[pos] = {"rostered_per_team": round(rostered, 2),
                    "backups_per_starter": round((rostered - starters) / starters, 2)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--derive", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    if args.derive or not args.fetch:
        print(json.dumps({f: derive(f) for f in FORMATS}, indent=1))


if __name__ == "__main__":
    main()
