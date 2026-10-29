#!/usr/bin/env python3
"""Build the JEG-1209 Fieldnotes revision 3 private preview (index.html).

Private design review only: nothing here is published (pipelines/build_v2_page.py and make sync never read preview/).

The page is assembled from three inputs, none of which this script changes:
  * the preserved revision-2 baseline from PR #1089 (docs/design/jeg-1209-fieldnotes/prototype.html, pinned by sha256):
    its CSS tokens/components, its embedded Fraunces font and its historical Week 7 fixture rows;
  * unchanged copies of the sibling components (vendor/, pinned by commit and git blob in vendor/MANIFEST.json);
  * this continuation's own markup, CSS and script (src/).

  python3 preview/jeg-1209-fieldnotes/build.py           writes index.html
  python3 preview/jeg-1209-fieldnotes/build.py --check   exits 1 when index.html, the baseline or a vendor file drifted
  python3 preview/jeg-1209-fieldnotes/build.py --vendor  re-copies vendor/ from the commits in MANIFEST.json (needs them fetched)
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = ROOT / "docs/design/jeg-1209-fieldnotes/prototype.html"
BASELINE_SHA256 = "f66e00c6f0098c46fcac6552943dfdcfc8f7b1302325c37a99c4ad1764adcf07"   # #1089 head 2c893123
BASELINE_COMMIT = "2c8931231ccd2bbeb4946ac031aee5ac655182f4"
OUT = HERE / "index.html"
VENDOR = HERE / "vendor"
# Load order matters: the stores first, then the components, then the Managers and Trade ideas cards that mount on them.
VENDOR_JS = ["workspace.js", "opportunities.js", "league-status.js", "opponent-inclusion.js", "column-order.js",
             "manager-profiles.js", "manager-recs.js", "manager-profiles-ui.js", "manager-recs-ui.js"]
VENDOR_CSS = ["league-status.css", "opponent-inclusion.css", "column-order.css", "manager-profiles.css"]


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest():
    return json.loads((VENDOR / "MANIFEST.json").read_text())


def check_inputs():
    problems = []
    if hashlib.sha256(BASELINE.read_bytes()).hexdigest() != BASELINE_SHA256:
        problems.append(f"baseline changed: {BASELINE.relative_to(ROOT)} no longer matches #1089 ({BASELINE_COMMIT[:8]})")
    for item in manifest()["files"]:
        if git_blob(VENDOR / item["file"]) != item["blob"]:
            problems.append(f"vendor/{item['file']} differs from {item['branch']} @ {item['commit'][:8]}")
    return problems


def baseline_parts():
    text = BASELINE.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)

    def const(name):
        line = next(l for l in text.splitlines() if l.startswith(f"const {name}="))
        return json.loads(line[len(f"const {name}="):].rstrip().rstrip(";"))

    data = const("DATA")
    fixture = {
        "baseline": {"pr": 1089, "commit": BASELINE_COMMIT, "path": str(BASELINE.relative_to(ROOT))},
        "provenance": data["provenance"],
        # Only what the cards read: identity and the value series. Numbers are copied, never rounded or edited.
        "players": [{k: p[k] for k in ("player_key", "name", "pos", "team", "values")} for p in data["players"]],
        "finder": const("FINDER_DATA"),
        "rosters": const("ROSTERS_DATA")["teams"],
    }
    return css, fixture


def build():
    css, fixture = baseline_parts()
    vendor_css = "\n".join(f"/* vendor/{n} */\n" + (VENDOR / n).read_text(encoding="utf-8") for n in VENDOR_CSS)
    vendor_js = "\n".join(f"</script><script>/* vendor/{n} */\n" + (VENDOR / n).read_text(encoding="utf-8") for n in VENDOR_JS)
    src = {n: (HERE / "src" / n).read_text(encoding="utf-8") for n in ("body.html", "continuation.css", "continuation.js")}
    pins = {m["file"]: f"{m['branch']}@{m['commit'][:8]}" for m in manifest()["files"]}
    head = ('<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            '<title>Find a trade: Fieldnotes r3 (private)</title>'
            f'<!-- Built by preview/jeg-1209-fieldnotes/build.py. Private design review, not published. Baseline #1089 {BASELINE_COMMIT[:8]}. Do not edit by hand. -->')
    fixture_js = "const FIXTURE=" + json.dumps(fixture, separators=(",", ":")).replace("</", "<\\/") + ";const VENDOR_PINS=" + json.dumps(pins) + ";"
    return (head + "<style>" + css + "</style><style>" + vendor_css + "</style><style>" + src["continuation.css"] + "</style></head><body>"
            + src["body.html"] + "<script>" + fixture_js + vendor_js + "</script><script>" + src["continuation.js"] + "</script></body></html>\n")


def refresh_vendor():
    for item in manifest()["files"]:
        data = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{item['commit']}:{item['path']}"])
        (VENDOR / item["file"]).write_bytes(data)


def main(argv):
    if "--vendor" in argv:
        refresh_vendor()
    problems = check_inputs()
    if "--check" in argv:
        if OUT.read_text(encoding="utf-8") != build():
            problems.append("index.html is stale: run python3 preview/jeg-1209-fieldnotes/build.py")
        print("\n".join(problems) if problems else "preview inputs and index.html match")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems))
        return 1
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
