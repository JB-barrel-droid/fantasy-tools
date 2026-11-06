#!/usr/bin/env python3
"""Capture FantasyPros Market's embedded JSON without executing page JavaScript.

JEG-1506 acquisition stage only. This deliberately emits a capture, NOT a
source-reference or comparison artifact. The row adapter, publisher timestamp,
and priced-row guards must be verified against a live page before promotion.
No capture can enter the comparison chain through this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SOURCE = "fantasypros_market"
BASE_URL = "https://www.fantasypros.com/nfl/myplaybook/trade-market-values/"
URLS = {"half_ppr": BASE_URL + "half-ppr", "ppr": BASE_URL + "ppr"}
# Intake: 550/551 rows. Protect the full embedded universe, including nulls.
MIN_ROWS = 400


class PullError(ValueError):
    """A missing, truncated, or changed source must never produce a capture."""


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


# Only locate declarations in executable script text. Strings, template
# literals, and comments are opaque; never evaluate a JavaScript expression.
_TOKEN = re.compile(
    r"\s+|//[^\n]*|/\*.*?\*/|"
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|"
    r"`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|.", re.S
)


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise PullError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _nonfinite(value):
    raise PullError(f"non-finite JSON number: {value}")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise PullError(f"non-finite JSON number: {value}")
    return result


def extract_initial_players(html: str, *, min_rows: int = MIN_ROWS):
    """Return the full JSON container; preserve every field and explicit null.

    Reject missing/duplicate declarations, executable JS expressions, duplicate
    JSON keys, and truncated universes. min_rows is injectable for unit tests.
    The source's row schema is intentionally not inferred by this extractor.
    """
    page = _Scripts()
    page.feed(html)
    decoder = json.JSONDecoder(object_pairs_hook=_object, parse_constant=_nonfinite, parse_float=_float)
    found = []
    for script in page.scripts:
        previous = []
        skip_until = 0
        for match in _TOKEN.finditer(script):
            if match.start() < skip_until:
                continue
            token = match.group()
            if token.isspace() or token.startswith(("//", "/*")):
                continue
            if token == "=" and previous[-2:] in (
                ["var", "initialPlayers"], ["let", "initialPlayers"],
                ["const", "initialPlayers"],
            ):
                start = match.end()
                while start < len(script) and script[start].isspace():
                    start += 1
                try:
                    players, end = decoder.raw_decode(script, start)
                except (ValueError, RecursionError) as exc:
                    raise PullError(f"initialPlayers is not plain JSON: {exc}") from exc
                if not script[end:].lstrip().startswith(";"):
                    raise PullError("initialPlayers must be a plain JSON assignment ending in ';'")
                found.append(players)
                skip_until = end
            previous = (previous + [token])[-2:]
    if len(found) != 1:
        raise PullError(f"expected one initialPlayers declaration, found {len(found)}")
    players = found[0]
    if not isinstance(players, (dict, list)) or len(players) < min_rows:
        size = len(players) if isinstance(players, (dict, list)) else 0
        raise PullError(f"initialPlayers universe too small: {size} (floor {min_rows})")
    rows = players.values() if isinstance(players, dict) else players
    if any(not isinstance(row, dict) or not row for row in rows):
        raise PullError("initialPlayers must contain nonempty player objects")
    return players


def fetch(scoring: str) -> str:
    request = urllib.request.Request(URLS[scoring], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200 or response.url.rstrip("/") != URLS[scoring]:
            raise PullError("publisher returned a non-200 response or unexpected redirect")
        return response.read().decode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scoring", choices=URLS, required=True)
    parser.add_argument("--out", required=True, help="acquisition capture JSON (not a publishable snapshot)")
    parser.add_argument("--html", help="replay a saved HTML page instead of fetching")
    args = parser.parse_args(argv)
    try:
        html = Path(args.html).read_text() if args.html else fetch(args.scoring)
        players = extract_initial_players(html)
        capture = {
            "schema": "fantasypros-market-acquisition-capture-v1",
            "source": SOURCE, "source_url": URLS[args.scoring], "scoring": args.scoring,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "acquisition": "saved_html_replay" if args.html else "live_http",
            "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "source_html": html,
            "source_values_timestamp": None,
            "publishable": False,
            "initialPlayers": players, "universe": len(players),
        }
    except (OSError, ValueError) as exc:
        print(f"FANTASYPROS MARKET CAPTURE FAILED: {exc}", file=sys.stderr)
        return 1
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    # All parsing/guards complete before touching an existing capture.
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(capture, indent=2, allow_nan=False) + "\n")
    temporary.replace(output)
    print(f"{SOURCE}/{args.scoring}: captured {len(players)} rows; not publishable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
