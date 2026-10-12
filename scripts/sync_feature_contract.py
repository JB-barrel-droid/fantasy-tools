"""Write the repo mirrors of Jeremy's Google Docs: the feature contract and the Manifesto.

The Docs are the source of truth. CI has no Google auth, so this script does not fetch
anything: export the Doc's text yourself (Drive connector read_file_content, or
File > Download > Markdown) and pass it in. The script only cleans the export and
adds the mirror header. It never changes a line of the Doc.

  contract  -> docs/feature-contract.md   (tests/test_v2_contract_render.py reads every ID)
  manifesto -> docs/manifesto-mirror.md   (MF-01 compares the rendered tab word for word)

Usage:
    python scripts/sync_feature_contract.py EXPORT.md                     # contract, from a file
    python scripts/sync_feature_contract.py - < EXPORT.md                 # contract, from stdin
    python scripts/sync_feature_contract.py --doc manifesto EXPORT.md     # the Manifesto
    python scripts/sync_feature_contract.py EXPORT.md --out other.md --date 2026-10-10
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    # v1.2 (2026-10-10). A new contract version may be a new Doc: update the URL here.
    "contract": {"url": "https://docs.google.com/document/d/1mI2vo4R74Fp-x14yR7ggh0T3WdcD6xjciLv7gVh4iJo",
                 "out": ROOT / "docs" / "feature-contract.md",
                 "reader": "tests/test_v2_contract_render.py reads every **XX-NN** ID below."},
    "manifesto": {"url": "https://docs.google.com/document/d/1YDJNHXLBUmLUuILnAFlEan7tuZgLzHH7Uk3NOFnCoOg",
                  "out": ROOT / "docs" / "manifesto-mirror.md",
                  "reader": "tests/test_v2_contract_render.py (MF-01) compares the rendered Manifesto tab with it word for word."},
}
MIRROR = DOCS["contract"]["out"]
DOC_URL = DOCS["contract"]["url"]
HEADER_END = "-->"
ID_LINE = re.compile(r"\*\*[A-Z]{2}-\d{2}\*\*")
# Markdown exports escape punctuation ("test\_v2\_contract"). Undo it, but keep "\*" so
# an escaped asterisk never turns into emphasis.
ESCAPE = re.compile(r"\\([\\`_{}\[\]()#+\-.!|>~])")


def header(date: str, doc: str = "contract") -> str:
    d = DOCS[doc]
    return (
        "<!--\n"
        f"Mirror of the Google Doc (source of truth): {d['url']}. Regenerate when the Doc changes; "
        f"never edit this file to change the {doc}.\n"
        f"Regenerate: python scripts/sync_feature_contract.py --doc {doc} <exported text>. Mirrored {date}.\n"
        f"{d['reader']}\n"
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


def render(export: str, date: str, doc: str = "contract") -> str:
    body = tidy_export(strip_header(export))
    if doc == "contract" and not ID_LINE.search(body):
        raise ValueError("the export has no **XX-NN** contract IDs; is this the right Doc?")
    if doc == "manifesto" and "Manifesto" not in body.split("\n", 1)[0]:
        raise ValueError("the export does not start with the Manifesto title; is this the right Doc?")
    return header(date, doc) + body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", help="exported Doc text (a file path, or - for stdin)")
    parser.add_argument("--doc", choices=sorted(DOCS), default="contract", help="which Doc the export is")
    parser.add_argument("--out", help="mirror to write (default: the Doc's mirror under docs/)")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="mirrored date for the header")
    args = parser.parse_args(argv)
    text = sys.stdin.read() if args.export == "-" else Path(args.export).read_text(encoding="utf-8")
    try:
        mirror = render(text, args.date, args.doc)
    except ValueError as error:
        print(f"sync_feature_contract: {error}", file=sys.stderr)
        return 1
    out = args.out or str(DOCS[args.doc]["out"])
    Path(out).write_text(mirror, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(ID_LINE.findall(mirror))} contract IDs)" if args.doc == "contract" else f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
