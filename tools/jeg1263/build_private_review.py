"""Build an isolated, unmerged real-provider review artifact; never publishes or fetches."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OVERLAYS = ("app/v2/simplified-site.js", "app/v2/simplified-site.css")

LOADER = r"""(() => {
  const query = new URLSearchParams(location.search);
  if (query.get('review-example') !== 'uso') return;
  const started = Date.now();
  function ready() {
    if (!window.TradeValueV2 || !window.TradeValueLeague?.ui.ready) {
      if (Date.now() - started < 60000) requestAnimationFrame(ready);
      return;
    }
    fetch('review-uso.json').then(r => {if(!r.ok) throw Error('Example unavailable');return r.json();}).then(fx => {
      TradeValueV2.applyLinkLeague(new URLSearchParams('scoring=half_ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN5'),{save:true});
      const W = TradeValueWorkspace, now = Date.now();
      let ws = W.newWorkspace({name:'Historical USO · Oct 29, 2026'});
      fx.league.teams.forEach(t => {ws = W.ops.addTeam(ws,'Team '+t.id,{entries:t.players.filter(p=>p.key).map(p=>
        ({key:p.key,name:p.name,pos:p.pos,slot:p.slot})),provenance:{unresolved:0,observedAt:now,editedAt:now,coverage:'unknown'}});});
      const mine = fx.league.teams.findIndex(t=>t.id===fx.mine);
      ws = W.ops.setMyTeam(ws,ws.teams[mine].id);
      W.store.replace(ws,'review:opt-in-example');
      query.delete('review-example');
      history.replaceState(history.state,'',location.pathname+(query.size?'?'+query:'')+location.hash);
    }).catch(error => {document.getElementById('privateReviewNotice').textContent='Example could not load: '+error.message;});
  }
  ready();
})();"""

LANDING = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DDF private working review</title><style>body{font:17px system-ui;max-width:720px;margin:32px auto;padding:20px;line-height:1.5}
a{display:inline-block;margin:8px 20px 8px 0;padding:12px;border:1px solid;border-radius:6px}strong{display:block}</style>
<h1>DDF private working review</h1><p>This is an unmerged review build with the real recommendation provider.
It uses historical fixtures and existing engine rules. The newly agreed starter-fit and market-source rules are pending JEG-1483;
this build does not claim to implement them.</p>
<nav aria-label="Review surfaces"><a href="index.html#simplified-site">Simplified site</a><a href="index.html#find-league">Full dashboard</a></nav>
<h2>Optional historical example</h2><p>Load the anonymized USO rosters from October 29, 2026. This explicitly replaces only this
private preview origin's saved workspace. Normal entry through either link above preserves your saved workspace.</p>
<a href="index.html?review-example=uso#simplified-site">Load historical USO example</a>
<p>Data dates and the preview's clock pin are recorded in <a href="review-manifest.json">the build manifest</a>.</p></html>"""


def build(provider_ref: str, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"Output must be a new directory: {output}")
    provider = subprocess.check_output(["git", "rev-parse", f"{provider_ref}^{{commit}}"], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(["git", "archive", provider], cwd=ROOT)
    overlay_bytes = {name: (ROOT / name).read_bytes() for name in OVERLAYS}
    with tempfile.TemporaryDirectory(prefix="ddf-private-review-") as temporary:
        checkout = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source_tar:
            source_tar.extractall(checkout, filter="data")
        for name, contents in overlay_bytes.items():
            (checkout / name).write_bytes(contents)
        env = {**os.environ, "RENDER_TESTS_REQUIRED": "1"}
        subprocess.run([os.sys.executable, "pipelines/sync_dashboard_artifacts.py"], cwd=checkout, env=env, check=True,
                       stdout=subprocess.DEVNULL, timeout=600)
        pin = subprocess.check_output([os.sys.executable, "-c", "from tests.test_week_history import _fixture_today; print(_fixture_today())"],
                                      cwd=checkout, env=env, text=True).strip()
        output.mkdir(parents=True)
        site = output / "site"
        shutil.copytree(checkout / "dist", site)
        shutil.copy2(checkout / "tests/fixtures/league_levels/uso.json", site / "review-uso.json")
        (site / "review-loader.js").write_text(LOADER, encoding="utf-8")
        (site / "review.html").write_text(LANDING, encoding="utf-8")
        shutil.copy2(ROOT / "tools/jeg1263/README.md", site / "INTEGRATION.md")
        index = site / "index.html"
        html = index.read_text(encoding="utf-8")
        html = html.replace("<head>", "<head><script>window.TRADE_VALUE_TODAY=" + json.dumps(pin) + ";</script>", 1)
        notice = '<aside id="privateReviewNotice" role="note" style="padding:8px 16px;border-bottom:1px solid">Private review · Historical data · Current engine rules. New starter-fit and market-source rules are pending.</aside>'
        body = html.index(">", html.index("<body")) + 1
        html = html[:body] + notice + html[body:]
        html = html.replace("</body>", '<script src="review-loader.js" defer></script></body>')
        index.write_text(html, encoding="utf-8")
        manifest = {"privateReviewOnly": True, "providerCommit": provider, "simplifiedCommit": source, "clockPin": pin,
                    "overlaySha256": {name: hashlib.sha256(data).hexdigest() for name, data in overlay_bytes.items()},
                    "overlayMatchesCommit": all(subprocess.check_output(["git", "show", f"{source}:{name}"], cwd=ROOT) == data
                                                for name, data in overlay_bytes.items()),
                    "builderSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "entry": "review.html", "unimplemented": ["JEG-1483 starter-fit and market-source changes"],
                    "publication": "none", "storage": "existing dashboard store; only opt-in example replaces preview workspace"}
        (site / "review-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def package(output: Path) -> Path:
    target = output / "ddf-private-review.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((output / "site").rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output / "site"))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-ref", required=True, help="An already fetched existing provider commit; no remote changes")
    parser.add_argument("--output", type=Path, required=True, help="New private output directory")
    args = parser.parse_args()
    manifest = build(args.provider_ref, args.output.resolve())
    print(json.dumps({**manifest, "bundle": str(package(args.output.resolve()))}, indent=2))
