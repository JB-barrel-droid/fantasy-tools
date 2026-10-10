"""Write docs/feature-contract.md, the mirror of Jeremy's feature contract Google Doc.

The Doc is the source of truth. CI has no Google auth, so this script does not fetch
anything: export the Doc's text yourself (Drive connector read_file_content, or
File > Download > Markdown) and pass it in. The script only cleans the export and
adds the mirror header. It never changes a contract line.

Usage:
    python scripts/sync_feature_contract.py EXPORT.md          # from a file
    python scripts/sync_feature_contract.py - < EXPORT.md      # from stdin
    python scripts/sync_feature_contract.py EXPORT.md --out other.md --date 2026-10-09
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "docs" / "feature-contract.md"
DOC_URL = "https://docs.google.com/document/d/1UDRlVTdOiAdI6gSSklxwB-R9uINozVmIILMwbvCBiH0"
HEADER_END = "-->"
ID_LINE = re.compile(r"\*\*[A-Z]{2}-\d{2}\*\*")
# Markdown exports escape punctuation ("test\_v2\_contract"). Undo it, but keep "\*" so
# an escaped asterisk never turns into emphasis.
ESCAPE = re.compile(r"\\([\\`_{}\[\]()#+\-.!|>~])")


def header(date: str) -> str:
    return (
        "<!--\n"
        f"Mirror of the Google Doc (source of truth): {DOC_URL}. Regenerate when the Doc changes; "
        "never edit this file to change the contract.\n"
        f"Regenerate: python scripts/sync_feature_contract.py <exported text>. Mirrored {date}.\n"
        "tests/test_v2_contract_render.py reads every **XX-NN** ID below.\n"
        f"{HEADER_END}\n\n"
    )


def tidy_export(text: str) -> str:
    """The Doc text with export noise removed: escapes, whitespace-only lines, blank runs."""
    lines = [ESCAPE.sub(r"\1", line).rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def strip_header(mirror: str) -> str:
    """The Doc body of an existing mirror (inverse of header())."""
    if mirror.startswith("<!--") and HEADER_END in mirror:
        return mirror.split(HEADER_END, 1)[1].lstrip("\n")
    return mirror


def render(export: str, date: str) -> str:
    body = tidy_export(strip_header(export))
    if not ID_LINE.search(body):
        raise ValueError("the export has no **XX-NN** contract IDs; is this the right Doc?")
    return header(date) + body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", help="exported Doc text (a file path, or - for stdin)")
    parser.add_argument("--out", default=str(MIRROR), help="mirror to write (default docs/feature-contract.md)")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="mirrored date for the header")
    args = parser.parse_args(argv)
    text = sys.stdin.read() if args.export == "-" else Path(args.export).read_text(encoding="utf-8")
    try:
        mirror = render(text, args.date)
    except ValueError as error:
        print(f"sync_feature_contract: {error}", file=sys.stderr)
        return 1
    Path(args.out).write_text(mirror, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(ID_LINE.findall(mirror))} contract IDs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
