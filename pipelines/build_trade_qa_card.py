#!/usr/bin/env python3
"""Bake the trade-dashboard QA card from modules/dashboard.html to JSON.

The card currently hardcodes qaData (round, date, errors, frameworks) in
modules/dashboard.html (lines 1458-1642). This script extracts those literal
fields and writes them to dist/modules/trade-qa-card.json so future QA rounds
can be baked without touching the HTML.

For now the builder only extracts what's already hardcoded -- it does NOT
design QA round-2/round-3 process or invent new findings. A future round-2
process would replace the literal source-of-truth (and this script would
read that source instead).

Output: dist/modules/trade-qa-card.json

Usage: python3 pipelines/build_trade_qa_card.py
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Path the dashboard fetches the JSON from at runtime. Documented here so a
# rename in one place surfaces in code review on the other.
DASHBOARD_HTML = REPO / "modules" / "dashboard.html"
OUTPUT_PATH = REPO / "dist" / "modules" / "trade-qa-card.json"

# Region of dashboard.html where the qaData literal lives. Kept narrow so
# other workers' edits outside this range don't accidentally get parsed.
SOURCE_LITERAL_START = 1458  # `const qaData = {`
SOURCE_LITERAL_END = 1642    # closing `};` of qaData


def _slice_dashboard_html(start_line: int, end_line: int) -> str:
    """Return the lines of dashboard.html in [start_line, end_line] inclusive.

    1-indexed, matching what an editor shows. The slice is the qaData
    literal -- the rest of the file is irrelevant for this extraction.
    """
    lines = DASHBOARD_HTML.read_text().splitlines()
    return "\n".join(lines[start_line - 1:end_line])


def _parse_qa_data_literal(slice_text: str) -> dict:
    """Parse the qaData = { ... }; literal into a Python dict.

    The literal uses a strict JS-object subset: no trailing commas, no
    comments, no template strings, no function values. Each entry has the
    shape `key: <json-compatible value>,`. We convert the slice into a
    JSON-compatible string by stripping the wrapping `const qaData = ...;`
    and converting JS-quoted keys to JSON-quoted keys.
    """
    text = slice_text.strip()
    # Strip the `const qaDataLiteral = ` prefix and trailing `;`. The
    # dashboard was edited to rename the hardcoded `qaData` to
    # `qaDataLiteral` because the literal now serves as a JSON-fetch
    # fallback. We track the live identifier here so a future rename
    # surfaces as a clear builder error.
    m = re.match(r"const\s+qaDataLiteral\s*=\s*(\{.*\})\s*;?\s*$", text, re.DOTALL)
    if not m:
        raise ValueError(
            "Could not locate `const qaDataLiteral = {...};` in the dashboard "
            "slice; the literal was edited in a way this builder does not "
            "recognise."
        )
    body = m.group(1)
    # JS object-literal keys are bare identifiers or strings; JSON requires
    # quoted strings. The literal uses bare identifiers consistently, so
    # convert `key:` -> `"key":` for top-level keys and for nested keys in
    # the schema we know about (id, severity, title, symptom, rootCause,
    # reasoning, status, fix, name, principle, rule, revealedBy,
    # futureApplication, check, fail). Numeric / string / boolean values
    # are unchanged; arrays and nested objects are handled by recursion.
    converted = _js_to_json(body)
    return json.loads(converted)


def _js_to_json(text: str) -> str:
    """Convert a JS object literal body to a JSON-compatible string.

    Strategy: walk the text character by character, tracking whether we are
    inside a double-quoted string. Only when we are NOT inside a string do
    we look for the pattern `identifier:` and quote the identifier. This
    handles the literal's strings that contain colons (e.g. the QA-001
    symptom mentions `Curves unavailable: Curve regression guard failed:
    sourceScaleAgreement`).

    JS string literals can also contain escaped quotes (`\"`) and escaped
    backslashes (`\\`). We track both so an escaped quote does not end the
    string early. The literal in dashboard.html uses straight double-quote
    strings only; single quotes do not appear inside the qaData block.
    """
    out = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                # Preserve the escape and the next char verbatim.
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        # Not in a string.
        if ch == '"':
            out.append(ch)
            in_string = True
            i += 1
            continue
        # Look for a bare-identifier key: word chars followed by optional
        # whitespace and then a colon. Skip if preceded by a word char (so
        # `foo12:baz` is treated as one token) or a quote (so we don't
        # touch the inside of any string we just left).
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            # Find the next non-whitespace char.
            k = j
            while k < n and text[k] in " \t\n\r":
                k += 1
            if k < n and text[k] == ":":
                out.append('"')
                out.append(text[i:j])
                out.append('"')
                out.append(":")
                i = k + 1
                continue
            out.append(text[i:j])
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_qa_data() -> dict:
    """Read the qaData literal from dashboard.html and return it as a dict."""
    slice_text = _slice_dashboard_html(SOURCE_LITERAL_START, SOURCE_LITERAL_END)
    return _parse_qa_data_literal(slice_text)


def build_trade_qa_card() -> dict:
    """Build the trade-qa-card payload that the dashboard will fetch.

    Round-1: bake the existing qaData literal. Future rounds would replace
    this function with the round-N extraction; the shape stays the same.
    """
    qa = extract_qa_data()
    # Keep only the four keys the brief calls out: round, date, errors,
    # frameworks. The HTML literal also has a `target` key used only by
    # the inline summary; drop it so the contract matches the brief.
    return {
        "round": qa["round"],
        "date": qa["date"],
        "errors": qa["errors"],
        "frameworks": qa["frameworks"],
    }


def main() -> int:
    payload = build_trade_qa_card()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  round: {payload['round']}")
    print(f"  date: {payload['date']}")
    print(f"  errors: {len(payload['errors'])}")
    print(f"  frameworks: {len(payload['frameworks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())