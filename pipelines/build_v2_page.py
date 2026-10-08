"""Build the v2 front end over the existing value engine.

The v2 layout (app/v2/) does no value math. It runs the current chart engine
(value-model.js, product-data.js, curve-widget.js) unchanged inside an
off-screen container and renders the new design from the engine's own rows,
so every number on v2 is the number the chart dashboard computes.

Input is the already-synced chart dashboard, dist/classic/index.html (data
islands and build tag included). Since launch (2026-10-08, Jeremy) v2 is the
site's front door, so it is written twice from that one input:

- dist/index.html: the root page. No <base>; the shell's "v2/#view" links
  become "#view" so tabs stay on this page.
- dist/v2/index.html: the same page for existing /v2/ and /v2/#view links,
  with <base href="../"> and a canonical pointing at the root.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_V2 = ROOT / "app" / "v2"
DIST = ROOT / "dist"

SITE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/"
CLASSIC_INPUT = Path("classic") / "index.html"
TITLE = "Data Driven Football"   # brand only (Jeremy, 2026-10-08)
DESCRIPTION = ("Rest-of-season fantasy football trade values for your league settings, "
               "trade targets where the published charts disagree with our values, "
               "and a trade calculator.")
OG_TITLE = TITLE
OG_DESCRIPTION = ("Rest-of-season trade values for your league settings, with trade targets "
                  "where the published charts disagree with our values.")

ENGINE_SCRIPT_MARKER = '<script src="assets/value-model.js'
LAST_ENGINE_SCRIPT = '<script src="assets/comparison-dashboard.js'

# At the root, links v2 builds at runtime as "v2/#view" (written for the /v2/
# copy, whose <base> is ../) would load /v2/ as a new page and drop in-memory
# state such as the trade being built. Keep them on this page.
ROOT_LINK_SHIM = """  <script>
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest ? event.target.closest('a[href^="v2/#"]') : null;
    if (!link || event.defaultPrevented || event.button !== 0
        || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    location.hash = link.getAttribute("href").slice(3);
  });
  </script>
"""


def _set_meta(html: str, attr: str, key: str, content: str) -> str:
    """Replace (or add) <meta {attr}="{key}" content="..."> in the head."""
    tag = f'<meta {attr}="{key}" content="{content}" />'
    pattern = re.compile(rf'<meta\s+{attr}="{re.escape(key)}"\s+content="[^"]*"\s*/?>')
    if pattern.search(html):
        return pattern.sub(lambda _m: tag, html, count=1)
    return html.replace("</head>", f"  {tag}\n</head>", 1)


def head_for_v2(html: str, at_root: bool) -> str:
    """v2's own head: title, description, social tags and canonical.

    The input is the classic page, whose head carries its own <base>,
    canonical and noindex; none of those may leak into v2.
    """
    html = re.sub(r'\n?\s*<base\s[^>]*>', "", html)
    html = re.sub(r'\n?\s*<link\s+rel="canonical"[^>]*>', "", html)
    html = re.sub(r'\n?\s*<meta\s+name="robots"[^>]*>', "", html)
    if not at_root:
        html = html.replace("<head>", '<head>\n  <base href="../">', 1)
    title_start = html.index("<title>")
    title_end = html.index("</title>") + len("</title>")
    html = html[:title_start] + f"<title>{TITLE}</title>" + html[title_end:]
    html = _set_meta(html, "name", "description", DESCRIPTION)
    html = _set_meta(html, "property", "og:title", OG_TITLE)
    html = _set_meta(html, "property", "og:description", OG_DESCRIPTION)
    html = _set_meta(html, "property", "og:url", SITE_URL)
    # v2 has a dark theme: let form controls follow it, and use the v2 nav colour for the browser bar.
    html = html.replace('<meta name="color-scheme" content="light" />', '<meta name="color-scheme" content="light dark" />', 1)
    html = html.replace('<meta name="theme-color" content="#17364c" />', '<meta name="theme-color" content="#142B25" />', 1)
    return html.replace("</head>", f'  <link rel="canonical" href="{SITE_URL}">\n</head>', 1)


def build_v2_html(index_html: str, shell_html: str, at_root: bool = False) -> str:
    for marker in ("<head>", "<body>", ENGINE_SCRIPT_MARKER, LAST_ENGINE_SCRIPT, "</title>"):
        if marker not in index_html:
            raise SystemExit(f"build_v2_page: marker {marker!r} missing from the chart dashboard page")
    html = head_for_v2(index_html, at_root)
    if at_root:
        shell_html = shell_html.replace('href="v2/#', 'href="#')
    head_extra = (
        '  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n'
        '  <link rel="stylesheet" href="v2/v2.css">\n'
        + (ROOT_LINK_SHIM if at_root else "")
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
    """Write dist/index.html (root) and dist/v2/index.html; return the /v2/ page."""
    index_html = (dist / CLASSIC_INPUT).read_text(encoding="utf-8")
    shell_html = (APP_V2 / "shell.html").read_text(encoding="utf-8")
    out_dir = dist / "v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_v2_html(index_html, shell_html), encoding="utf-8")
    (dist / "index.html").write_text(build_v2_html(index_html, shell_html, at_root=True), encoding="utf-8")
    for name in ("v2.css", "targets.js", "trade.js", "movers.js", "v2.js"):
        shutil.copy2(APP_V2 / name, out_dir / name)
    return out_dir / "index.html"


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
