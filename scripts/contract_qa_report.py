"""Contract QA report (JEG-491): run every automatable feature-contract check, write
docs/qa-report.md with per-ID pass/fail plus the pending ("to build") gaps, and exit
non-zero when any live line fails.

Run before a review publish:  python scripts/contract_qa_report.py
Options: --out PATH (default docs/qa-report.md), --ids GL-01 PV-02 (subset),
         --status JEG-498=Todo JEG-503=Done (ticket status shown for pending lines).
The checks themselves live in tests/test_v2_contract_render.py; this only reports.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def line_summaries(text: str) -> dict[str, str]:
    """{ID: first sentence of the line, trimmed}."""
    out = {}
    for line in text.splitlines():
        m = re.search(r"\*\*([A-Z]{2}-\d{2})\*\*", line)
        if m:
            body = re.sub(r"\*+|\(to build:[^)]*\)", "", line[m.end():]).strip()
            out[m.group(1)] = (body.split(". ")[0] or "")[:110]
    return out


def render_report(live: dict, pending: dict, summaries: dict, stamp: str,
                  page_errors=(), status=None) -> str:
    """live: {ID: [errors]}; pending: {ID: ticket}; both from the contract run."""
    status = status or {}
    failing = {c: e for c, e in live.items() if e}
    lines = [
        "# Contract QA report", "",
        f"Generated {stamp} by scripts/contract_qa_report.py. "
        "Do not edit; rerun the script.", "",
        f"**Result: {'FAIL' if failing or page_errors else 'PASS'}** "
        f"({len(live) - len(failing)} of {len(live)} live lines pass, {len(pending)} pending)", "",
        "## Live lines", "", "| ID | Result | Line / finding |", "|---|---|---|",
    ]
    for cid in sorted(live):
        errs = live[cid]
        note = summaries.get(cid, "") if not errs else "; ".join(e.replace("|", "/") for e in errs[:3])
        lines.append(f"| {cid} | {'FAIL' if errs else 'pass'} | {note} |")
    if page_errors:
        lines += ["", "## Page errors", ""] + [f"- {e}" for e in page_errors]
    lines += ["", "## Pending (to build)", "", "| ID | Ticket | Ticket status | Line |", "|---|---|---|---|"]
    for cid in sorted(pending):
        ticket = pending[cid]
        lines.append(f"| {cid} | {ticket} | {status.get(ticket, 'unknown')} | {summaries.get(cid, '')} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "qa-report.md"))
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--status", nargs="*", default=[], metavar="JEG-1=State")
    args = ap.parse_args(argv)

    from datetime import datetime, timezone
    from tests import test_v2_contract_render as contract
    contract.setUpModule()
    results, page_errors = contract.run_contract(args.ids or None)
    pending = {cid: c.ticket for cid, c in contract.CHECKS.items()
               if isinstance(c, contract.PENDING)}
    summaries = line_summaries(contract.MIRROR.read_text(encoding="utf-8"))
    status = dict(s.split("=", 1) for s in args.status)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    Path(args.out).write_text(render_report(results, pending, summaries, stamp, page_errors, status),
                              encoding="utf-8")
    failing = [c for c, e in results.items() if e]
    print(f"{len(results) - len(failing)}/{len(results)} live lines pass; "
          f"{len(pending)} pending; report -> {args.out}")
    if failing:
        print("FAIL: " + ", ".join(failing))
    return 1 if failing or page_errors else 0


if __name__ == "__main__":
    sys.exit(main())
