"""Build dist/v2/index.html: the v2 front end over the existing value engine.

The v2 layout (app/v2/) does no value math. It runs the current chart engine
(value-model.js, product-data.js, curve-widget.js) unchanged inside an
off-screen container and renders the new design from the engine's own rows,
so every number on /v2/ is the number the current page computes.

Input is the already-synced dist/index.html (data islands and build tag
included); output is dist/v2/index.html plus the v2 assets.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_V2 = ROOT / "app" / "v2"
DIST = ROOT / "dist"

ENGINE_SCRIPT_MARKER = '<script src="assets/value-model.js'
LAST_ENGINE_SCRIPT = '<script src="assets/comparison-dashboard.js'


def build_v2_html(index_html: str, shell_html: str) -> str:
    for marker in ("<head>", "<body>", ENGINE_SCRIPT_MARKER, LAST_ENGINE_SCRIPT, "</title>"):
        if marker not in index_html:
            raise SystemExit(f"build_v2_page: marker {marker!r} missing from dist/index.html")
    html = index_html.replace("<head>", '<head>\n  <base href="../">', 1)
    title_start = html.index("<title>")
    title_end = html.index("</title>") + len("</title>")
    html = html[:title_start] + "<title>Trade Value · Data Driven Football</title>" + html[title_end:]
    # v2 has a dark theme: let form controls follow it, and use the v2 nav colour for the browser bar.
    html = html.replace('<meta name="color-scheme" content="light" />', '<meta name="color-scheme" content="light dark" />', 1)
    html = html.replace('<meta name="theme-color" content="#17364c" />', '<meta name="theme-color" content="#142B25" />', 1)
    head_extra = (
        '  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n'
        '  <link rel="stylesheet" href="v2/v2.css">\n'
    )
    html = html.replace("</head>", head_extra + "</head>", 1)
    html = html.replace(
        "<body>",
        '<body class="v2">\n' + shell_html
        + '\n<div id="legacyEngine" class="legacy-engine" aria-hidden="true" inert>',
        1,
    )
    engine_at = html.index(ENGINE_SCRIPT_MARKER)
    html = html[:engine_at] + "</div>\n  " + html[engine_at:]
    last_at = html.index(LAST_ENGINE_SCRIPT)
    line_end = html.index("</script>", last_at) + len("</script>")
    v2_scripts = ('\n  <script src="v2/targets.js" defer></script>'
                  '\n  <script src="v2/trade.js" defer></script>'
                  '\n  <script src="v2/movers.js" defer></script>'
                  '\n  <script src="v2/v2.js" defer></script>')
    html = html[:line_end] + v2_scripts + html[line_end:]
    return html


def build(dist: Path = DIST) -> Path:
    index_html = (dist / "index.html").read_text(encoding="utf-8")
    shell_html = (APP_V2 / "shell.html").read_text(encoding="utf-8")
    out_dir = dist / "v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_v2_html(index_html, shell_html), encoding="utf-8")
    for name in ("v2.css", "targets.js", "trade.js", "movers.js", "v2.js"):
        shutil.copy2(APP_V2 / name, out_dir / name)
    return out_dir / "index.html"


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
