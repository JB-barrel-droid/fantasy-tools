"""Build the v2 front end over the existing value engine.

The v2 layout (app/v2/) does no value math. It runs the current chart engine
(value-model.js, product-data.js, curve-widget.js) unchanged inside an
off-screen container and renders the new design from the engine's own rows,
so every number on v2 is the number the chart dashboard computes.

Input is the already-synced engine page, build/engine/index.html (the old
chart dashboard, data islands and build tag included; build-only since
JEG-453, never published). Since launch (2026-10-08, Jeremy) v2 is the
site's front door, so it is written twice from that one input:

- dist/index.html: the root page. No <base>; the shell's "v2/#view" links
  become "#view" so tabs stay on this page.
- dist/v2/index.html: the same page for existing /v2/ and /v2/#view links,
  with <base href="../"> and a canonical pointing at the root.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_V2 = ROOT / "app" / "v2"
DIST = ROOT / "dist"
RESEARCH_DIR = APP_V2 / "research"
# Sleeper /players/nfl, refreshed twice a week by .github/workflows/sleeper-identity-refresh.yml.
SLEEPER_BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
NFL_BYES = ROOT / "data" / "inputs" / "nfl_byes_2026.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

# The 32 team defenses (name, team code as roster-paste.js writes it: Jacksonville is JAC). The engine prices no
# defense (JEG-988), so Find a trade offers these by name as unpriced "Not evaluated" entries (JEG-995).
DEFENSES = [
    ("Arizona Cardinals", "ARI"), ("Atlanta Falcons", "ATL"), ("Baltimore Ravens", "BAL"), ("Buffalo Bills", "BUF"),
    ("Carolina Panthers", "CAR"), ("Chicago Bears", "CHI"), ("Cincinnati Bengals", "CIN"), ("Cleveland Browns", "CLE"),
    ("Dallas Cowboys", "DAL"), ("Denver Broncos", "DEN"), ("Detroit Lions", "DET"), ("Green Bay Packers", "GB"),
    ("Houston Texans", "HOU"), ("Indianapolis Colts", "IND"), ("Jacksonville Jaguars", "JAC"), ("Kansas City Chiefs", "KC"),
    ("Las Vegas Raiders", "LV"), ("Los Angeles Chargers", "LAC"), ("Los Angeles Rams", "LAR"), ("Miami Dolphins", "MIA"),
    ("Minnesota Vikings", "MIN"), ("New England Patriots", "NE"), ("New Orleans Saints", "NO"), ("New York Giants", "NYG"),
    ("New York Jets", "NYJ"), ("Philadelphia Eagles", "PHI"), ("Pittsburgh Steelers", "PIT"), ("San Francisco 49ers", "SF"),
    ("Seattle Seahawks", "SEA"), ("Tampa Bay Buccaneers", "TB"), ("Tennessee Titans", "TEN"), ("Washington Commanders", "WAS"),
]

SITE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/"
# The engine page sync_dashboard_artifacts writes. Outside dist/, so Pages never
# serves it (JEG-453); /classic/ in dist/ is a redirect to the root.
ENGINE_PAGE = ROOT / "build" / "engine" / "index.html"
TITLE = "Data Driven Football"   # brand only (Jeremy, 2026-10-08)
DESCRIPTION = ("Know who to trade for, before your league does. Fantasy football trade values "
               "built for your league, plus the trades your league-mates will actually say yes to.")
OG_TITLE = TITLE
OG_DESCRIPTION = ("Trade values built for your league, plus the trades your league-mates "
                  "will actually say yes to.")

# JEG-1026: the footer line "Using ChatGPT or Claude? Connect the tool" on every tab (static HTML), linking the connect guide that
# build_llm_surfaces.py publishes at connect/ (shell.html carries the same URL literally: the contract test needs the built page to embed it verbatim). The marker is where the footer starts in shell.html.
ASSIST_FOOTER_MARKER = "<!-- JEG-1026: on every tab"
CONNECT_URL = SITE_URL + "connect/"

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


# Page weight (2026-10-08): the engine scripts each fetch the same JSON files
# (comparison-sources-data.json is 2.3 MB and was downloaded and parsed three
# times). Share one network request per URL; every caller gets its own clone of
# the response, and a caller's own abort signal still rejects that caller.
FETCH_SHARE_SHIM = r"""  <script>
  (function () {
    var nativeFetch = window.fetch && window.fetch.bind(window);
    if (!nativeFetch) return;
    var shared = new Map();
    window.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
      if (method !== "GET" || !/\.json(\?|$)/.test(url)) return nativeFetch(input, init);
      var key = new URL(url, document.baseURI).href;
      if (!shared.has(key)) {
        var request = nativeFetch(key).catch(function (error) { shared.delete(key); throw error; });
        shared.set(key, request);
      }
      var signal = init && init.signal;
      var mine = shared.get(key).then(function (response) { return response.clone(); });
      if (!signal) return mine;
      return new Promise(function (resolve, reject) {
        var abort = function () { reject(new DOMException("The operation was aborted.", "AbortError")); };
        if (signal.aborted) return abort();
        signal.addEventListener("abort", abort, {once: true});
        mine.then(resolve, reject);
      });
    };
  })();
  </script>
"""

# The classic page's own fonts; v2 uses Inter only, and the engine is never shown.
CLASSIC_FONTS = re.compile(r'\n?\s*<link href="https://fonts\.googleapis\.com/css2\?family=Archivo[^"]*" rel="stylesheet">')


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
    # JEG-1028: a machine-readable pointer for AI assistants (what the site is, the MCP server, the skill).
    return html.replace(
        "</head>",
        f'  <link rel="canonical" href="{SITE_URL}">\n'
        f'  <link rel="alternate" type="text/plain" title="For AI assistants" href="{SITE_URL}llms.txt">\n</head>',
        1,
    )


# ---------- Research tab (JEG-543) ----------
# One file per post in app/v2/research/<slug>.html. The first line is a comment holding the post's
# metadata as JSON: <!--post {"title": ..., "summary": ..., "date": "2026-10-12", "published": true} -->.
# The rest is the post body (HTML). A post without "published": true is a draft and never reaches the build.
# "published" is set only after Jeremy approves the Google Doc draft.
POST_META = re.compile(r"\A\s*<!--post\s*(\{.*?\})\s*-->", re.S)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _nice_date(iso: str) -> str:
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{MONTHS[month - 1]} {day}, {year}"


def load_posts(research_dir: Path = RESEARCH_DIR) -> list[dict]:
    """Published posts, newest first. Drafts are skipped; a malformed file is an error, not a silent skip."""
    posts = []
    for path in sorted(research_dir.glob("*.html")) if research_dir.is_dir() else []:
        text = path.read_text(encoding="utf-8")
        match = POST_META.match(text)
        if not match:
            raise SystemExit(f"build_v2_page: {path.name} has no <!--post {{...}}--> metadata line")
        meta = json.loads(match.group(1))
        if meta.get("published") is not True:
            continue
        if not SLUG.match(path.stem):
            raise SystemExit(f"build_v2_page: research slug {path.stem!r} must be lowercase words joined by hyphens")
        for key in ("title", "summary", "date"):
            if not str(meta.get(key, "")).strip():
                raise SystemExit(f"build_v2_page: {path.name} is published but has no {key}")
        posts.append({"slug": path.stem, "title": meta["title"], "summary": meta["summary"],
                      "date": meta["date"], "body": text[match.end():].strip()})
    return sorted(posts, key=lambda post: (post["date"], post["slug"]), reverse=True)


def research_html(posts: list[dict]) -> str:
    """The Research section: an index of posts plus one hidden article per post (#writing/research/<slug>)."""
    esc = html_lib.escape
    if posts:
        rows = "\n".join(
            f'        <li><a class="v2-rs-link" href="#writing/research/{post["slug"]}">{esc(post["title"])}</a>'
            f'<span class="v2-rs-sum">{esc(post["summary"])}</span>'
            f'<time class="v2-rs-date" datetime="{post["date"]}">{_nice_date(post["date"])}</time></li>'
            for post in posts)
        index_body = f'      <ul class="v2-rs-list">\n{rows}\n      </ul>'
    else:
        index_body = '      <p class="v2-rs-empty">Nothing is published here yet. Posts will show how we tested the choices behind the values. Until then, <a href="#writing/how-values">How values work</a> and the <a href="#writing/manifesto">Manifesto</a> explain the method.</p>'
    articles = "\n".join(
        f'    <article class="v2-mf-text v2-rs-post" id="v2Post-{post["slug"]}" data-slug="{post["slug"]}" hidden>\n'
        f'      <p class="v2-mf-eyebrow"><a href="#writing/research">Research</a></p>\n'
        f'      <h1>{esc(post["title"])}</h1>\n'
        f'      <p class="v2-rs-meta"><time datetime="{post["date"]}">{_nice_date(post["date"])}</time></p>\n'
        f'{post["body"]}\n'
        f'      <p class="v2-rs-back"><a href="#writing/research">All research</a> · <a href="#writing/manifesto">Manifesto</a></p>\n'
        f'    </article>' for post in posts)
    return (
        '\n  <!-- Research (JEG-543): built from app/v2/research/*.html, published posts only. -->\n'
        '  <main class="v2-wrap v2-main v2-mf" id="v2Research" hidden aria-labelledby="v2ResearchTitle">\n'
        '    <article class="v2-mf-text v2-rs-index" id="v2ResearchIndex">\n'
        '      <p class="v2-mf-eyebrow">Data Driven Football</p>\n'
        '      <h1 id="v2ResearchTitle">Research</h1>\n'
        '      <p>The evidence behind the choices this tool makes, and how we arrived at them. '
        'The <a href="#writing/manifesto">Manifesto</a> states the principles; these posts show the work.</p>\n'
        f'{index_body}\n'
        '    </article>\n'
        f'{articles}\n'
        '  </main>\n')


def compose_shell(shell_html: str, posts: list[dict]) -> str:
    """shell.html with the built Research page placed inside #v2App (the only body child the page shows)."""
    end = shell_html.rstrip().rfind("</div>")
    if end < 0:
        raise SystemExit("build_v2_page: shell.html has no closing </div> for #v2App")
    # JEG-1026: the ChatGPT / Claude footer stays the last thing on the page, so the Research tab goes in before it.
    foot = shell_html.find(ASSIST_FOOTER_MARKER)
    if foot >= 0:
        end = shell_html.rfind("\n", 0, foot) + 1
    return shell_html[:end] + research_html(posts) + shell_html[end:]


def build_v2_html(index_html: str, shell_html: str, at_root: bool = False, posts: list[dict] | None = None) -> str:
    for marker in ("<head>", "<body>", ENGINE_SCRIPT_MARKER, LAST_ENGINE_SCRIPT, "</title>"):
        if marker not in index_html:
            raise SystemExit(f"build_v2_page: marker {marker!r} missing from the chart dashboard page")
    html = head_for_v2(index_html, at_root)
    html = CLASSIC_FONTS.sub("", html, count=1)
    if at_root:
        shell_html = shell_html.replace('href="v2/#', 'href="#')
    head_extra = (
        '  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n'
        '  <link rel="stylesheet" href="v2/v2.css">\n'
        '  <link rel="stylesheet" href="v2/audit-pie.css">\n'
        '  <link rel="stylesheet" href="v2/audit-source.css">\n'
        '  <link rel="stylesheet" href="v2/waivers.css">\n'
        '  <link rel="stylesheet" href="v2/overrides.css">\n'
        # JEG-1137: ?design=fieldnotes opts into the Fieldnotes layer; synchronous so it applies before first paint.
        '  <script src="v2/design-flag.js"></script>\n'
        + FETCH_SHARE_SHIM
        + (ROOT_LINK_SHIM if at_root else "")
    )
    html = html.replace("</head>", head_extra + "</head>", 1)
    html = html.replace(
        "<body>",
        '<body class="v2">\n' + compose_shell(shell_html, load_posts() if posts is None else posts)
        + '\n<div id="legacyEngine" class="legacy-engine" aria-hidden="true" inert>',
        1,
    )
    engine_at = html.index(ENGINE_SCRIPT_MARKER)
    html = html[:engine_at] + "</div>\n  " + html[engine_at:]
    last_at = html.index(LAST_ENGINE_SCRIPT)
    line_end = html.index("</script>", last_at) + len("</script>")
    v2_scripts = ('\n  <script src="assets/player-tags.js" defer></script>'
                  '\n  <script src="v2/namesearch.js" defer></script>'
                  '\n  <script src="v2/source-views.js" defer></script>'
                  '\n  <script src="v2/targets.js" defer></script>'
                  '\n  <script src="v2/trade.js" defer></script>'
                  '\n  <script src="v2/movers.js" defer></script>'
                  '\n  <script src="v2/kdef-names.js" defer></script>'
                  '\n  <script src="v2/roster-paste.js" defer></script>'
                  '\n  <script src="v2/workspace.js" defer></script>'
                  '\n  <script src="v2/table-sort.js" defer></script>'
                  '\n  <script src="v2/team-summary.js" defer></script>'
                  '\n  <script src="v2/opportunities.js" defer></script>'
                  '\n  <script src="v2/finder.js" defer></script>'
                  '\n  <script src="v2/lineup-comparison.js" defer></script>'
                  '\n  <script src="v2/league.js" defer></script>'
                  '\n  <script src="v2/nfl-byes.js" defer></script>'
                  '\n  <script src="v2/player-status.js" defer></script>'
                  '\n  <script src="v2/waivers.js" defer></script>'
                  '\n  <script src="v2/modules.js" defer></script>'
                  '\n  <script src="v2/audit-core.js" defer></script>'
                  '\n  <script src="v2/audit-pie.js" defer></script>'
                  '\n  <script src="v2/audit-source.js" defer></script>'
                  '\n  <script src="v2/overrides.js" defer></script>'
                  '\n  <script src="v2/inputs-status.js" defer></script>'
                  '\n  <script src="v2/name-format.js" defer></script>'
                  '\n  <script src="v2/ddf-state.js" defer></script>'
                  '\n  <script src="v2/trade-context.js" defer></script>'
                  '\n  <script src="v2/ddf-assist.js" defer></script>'
                  '\n  <script src="v2/v2.js" defer></script>')
    html = html[:line_end] + v2_scripts + html[line_end:]
    return html


def kdef_names_js(base_path: Path = SLEEPER_BASE) -> str:
    """window.TradeValueKDef: the 32 defenses and the kickers on an NFL team now, for Find a trade's typed search (JEG-995).

    Kickers come from the Sleeper identity base (position K with a current team: Sleeper leaves a free agent's team
    empty, and the base keeps retired kickers marked active, so a team is the only current signal). Derived at build
    time, so the twice-weekly Sleeper refresh is the refresh path and nothing generated is committed. A missing base
    gives defenses only."""
    kickers, pulled_at = [], None
    if base_path.exists():
        base = json.loads(base_path.read_text(encoding="utf-8"))
        pulled_at = (base.get("meta") or {}).get("pulled_at")
        seen = set()
        for player in (base.get("by_sleeper_id") or {}).values():
            if player.get("pos") == "K" and player.get("team") and player.get("name") and player["name"] not in seen:
                seen.add(player["name"])
                kickers.append({"name": player["name"], "team": player["team"]})
        kickers.sort(key=lambda k: k["name"])
    data = {"defenses": [{"name": n, "team": t} for n, t in DEFENSES], "kickers": kickers, "kickers_pulled_at": pulled_at}
    return "window.TradeValueKDef = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"


def nfl_byes_js(path: Path = NFL_BYES) -> str:
    """window.TradeValueByes: each team's bye week this season, for the Waivers tab's bye-week coverage (JEG-1022).

    Read from data/inputs/nfl_byes_2026.json (the file the pipelines use), so nothing is typed twice and nothing generated
    is committed. A missing file gives no byes: the tab then says nothing about byes, never a guess."""
    byes = {}
    season = None
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        season = data.get("season")
        byes = {team: week for team, week in (data.get("byes") or {}).items() if isinstance(week, int)}
    return "window.TradeValueByes = " + json.dumps({"season": season, "byes": byes}, separators=(",", ":")) + ";\n"


def player_status_js(path: Path = PLAYERS) -> str:
    """window.TradeValueStatus: when the injury status on players.json rows was pulled from Sleeper (JEG-1312).

    The rows' injury_status comes from the Sleeper identity base the bake read, and the bake records that base's
    pulled_at in meta.universe.nfl_active.identity_base_pulled_at, so this is the date of the status the page actually
    ships (not today's Supabase snapshot). A missing file or date gives as_of null: the Waivers tab then shows no
    status, never an undated one."""
    as_of = None
    if path.exists():
        meta = json.loads(path.read_text(encoding="utf-8")).get("meta") or {}
        as_of = ((meta.get("universe") or {}).get("nfl_active") or {}).get("identity_base_pulled_at")
    data = {"source": "Sleeper", "as_of": as_of if isinstance(as_of, str) and as_of else None}
    return "window.TradeValueStatus = " + json.dumps(data, separators=(",", ":")) + ";\n"


def build(dist: Path = DIST, engine_page: Path = ENGINE_PAGE, research_dir: Path = RESEARCH_DIR) -> Path:
    """Write dist/index.html (root) and dist/v2/index.html; return the /v2/ page."""
    index_html = engine_page.read_text(encoding="utf-8")
    shell_html = (APP_V2 / "shell.html").read_text(encoding="utf-8")
    out_dir = dist / "v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    posts = load_posts(research_dir)
    (out_dir / "index.html").write_text(build_v2_html(index_html, shell_html, posts=posts), encoding="utf-8")
    (dist / "index.html").write_text(build_v2_html(index_html, shell_html, at_root=True, posts=posts), encoding="utf-8")
    (out_dir / "kdef-names.js").write_text(kdef_names_js(), encoding="utf-8")
    (out_dir / "nfl-byes.js").write_text(nfl_byes_js(), encoding="utf-8")
    (out_dir / "player-status.js").write_text(player_status_js(), encoding="utf-8")
    for name in ("v2.css", "namesearch.js", "source-views.js", "targets.js", "trade.js", "movers.js", "roster-paste.js", "workspace.js", "table-sort.js", "team-summary.js", "opportunities.js", "finder.js", "lineup-comparison.js", "league.js", "modules.js",
                 "audit-core.js", "audit-pie.js", "audit-source.js", "audit-pie.css", "audit-source.css", "overrides.js", "overrides.css", "inputs-status.js", "name-format.js", "ddf-state.js", "trade-context.js", "ddf-assist.js", "waivers.js", "waivers.css", "design-flag.js", "v2.js"):
        shutil.copy2(APP_V2 / name, out_dir / name)
    # JEG-1137: self-hosted Fraunces (SIL OFL 1.1, license kept beside it), read by v2.css as fonts/fraunces.woff2.
    (out_dir / "fonts").mkdir(exist_ok=True)
    for name in ("fraunces.woff2", "FONT-LICENSE.txt"):
        shutil.copy2(APP_V2 / "fonts" / name, out_dir / "fonts" / name)
    return out_dir / "index.html"


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
