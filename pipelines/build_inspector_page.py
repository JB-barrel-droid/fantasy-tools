"""Build the internal math inspector over the existing value engine.

The inspector (app/inspector/) does no value math. Like the v2 page
(build_v2_page.py) it runs the chart engine (value-model.js, product-data.js,
curve-widget.js) unchanged inside an off-screen container, and renders every
input and intermediate number from the engine's read-only accessor
TradeValueCurveControls.getInspection(), so every number it shows is the
number the chart computes.

Input is the already-synced chart page, dist/classic/index.html. Output is
dist/modules/math-inspector.html: internal, noindex, nofollow, linked from no
public page (launch decision 2026-10-08). It sits one directory down from the
site root like /classic/, so the classic page's <base href="../"> keeps every
asset and data path working.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_INSPECTOR = ROOT / "app" / "inspector"
DIST = ROOT / "dist"

CLASSIC_INPUT = Path("classic") / "index.html"
OUTPUT = Path("modules") / "math-inspector.html"
ASSETS = ("math-inspector.js", "math-inspector.css")
TITLE = "Math Inspector · Data Driven Football (internal)"

ENGINE_SCRIPT_MARKER = '<script src="assets/value-model.js'
LAST_ENGINE_SCRIPT = '<script src="assets/comparison-dashboard.js'


def build_inspector_html(classic_html: str, shell_html: str) -> str:
    for marker in ("<head>", "<body>", '<base href="../">', ENGINE_SCRIPT_MARKER,
                   LAST_ENGINE_SCRIPT, "</title>"):
        if marker not in classic_html:
            raise SystemExit(f"build_inspector_page: marker {marker!r} missing from the classic page")
    html = re.sub(r'\n?\s*<link\s+rel="canonical"[^>]*>', "", classic_html)
    html = re.sub(r'\n?\s*<meta\s+name="robots"[^>]*>', "", html)
    title_start = html.index("<title>")
    title_end = html.index("</title>") + len("</title>")
    html = (html[:title_start] + f"<title>{TITLE}</title>"
            + '\n  <meta name="robots" content="noindex, nofollow">'
            + html[title_end:])
    stamp = re.search(r'<script src="assets/value-model\.js(\?v=[^"]*)?"', html)
    version = (stamp.group(1) or "") if stamp else ""
    html = html.replace(
        "</head>", f'  <link rel="stylesheet" href="modules/math-inspector.css{version}">\n</head>', 1)
    html = html.replace(
        "<body>",
        '<body class="inspector">\n' + shell_html
        + '\n<div id="inspectorEngine" class="inspector-engine" aria-hidden="true">',
        1,
    )
    engine_at = html.index(ENGINE_SCRIPT_MARKER)
    html = html[:engine_at] + "</div>\n  " + html[engine_at:]
    last_at = html.index(LAST_ENGINE_SCRIPT)
    line_end = html.index("</script>", last_at) + len("</script>")
    html = (html[:line_end]
            + f'\n  <script src="modules/math-inspector.js{version}" defer></script>'
            + html[line_end:])
    return html


def build(dist: Path = DIST) -> Path:
    classic_html = (dist / CLASSIC_INPUT).read_text(encoding="utf-8")
    shell_html = (APP_INSPECTOR / "shell.html").read_text(encoding="utf-8")
    out = dist / OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_inspector_html(classic_html, shell_html), encoding="utf-8")
    for name in ASSETS:
        shutil.copy2(APP_INSPECTOR / name, out.parent / name)
    return out


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
