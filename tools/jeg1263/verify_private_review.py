"""Exercise an already-built private artifact with the real provider; no live network or production writes."""
from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

SAVED = "() => TradeValueWorkspace.serialize(TradeValueWorkspace.store.get())"


def verify(site: Path, evidence: Path) -> dict:
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"provider": "real #1084", "widths": [], "states": [], "pageErrors": []}

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    with contextlib.ExitStack() as stack:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
        stack.callback(server.server_close)
        stack.callback(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        pw = stack.enter_context(sync_playwright())
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                                     args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"])
        stack.callback(browser.close)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda err: report["pageErrors"].append(str(err)))
        page.route(lambda url: not url.startswith(base), lambda route: route.abort())
        page.goto(base + "/index.html#simplified-site", wait_until="networkidle")
        page.wait_for_selector("#v2Simplified[data-state=empty]")
        report["states"].append("empty: real empty workspace")
        page.goto(base + "/index.html?review-example=uso#simplified-site", wait_until="networkidle")
        page.wait_for_selector("#v2Simplified[data-state=answer]", timeout=180000)
        page.wait_for_function("() => !TradeValueLeague.ui.running && !TradeValueLeague.ui.timer")
        before = page.evaluate(SAVED)
        assert page.evaluate("typeof TradeValueTradeIdeas.compute") == "function"
        baseline = page.evaluate("""() => {const x=TradeValueTradeIdeas.compute();return {
          ids:x.recommendations.slice(0,10).map(r=>r.id),gains:x.recommendations.slice(0,10).map(r=>r.ourGain),
          count:x.recommendations.length,opportunities:TradeValueLeague.ui.result.rows.length};}""")
        assert baseline["count"] > 0
        report["realRecommendations"] = baseline["count"]
        report["realOpportunities"] = baseline["opportunities"]
        report["states"].append("answer: real completed search/provider")
        for width in (1280, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.get_by_role("link", name="Full dashboard", exact=True).click()
            page.wait_for_selector("#v2LgCard")
            page.wait_for_function("() => document.querySelectorAll('#v2MiList > li[data-trade-id]').length > 0")
            full = page.locator("#v2MiList > li[data-trade-id]").evaluate_all("ns=>ns.map(n=>({id:n.dataset.tradeId,gain:n.querySelector('.v2-mi-gain').textContent}))")
            assert [r["id"] for r in full] == baseline["ids"]
            page.evaluate("location.hash='#simplified-site'")
            page.wait_for_selector("#v2Simplified[data-state=answer]")
            view = page.evaluate("""() => {const S=TradeValueSimplifiedSite,c=S.liveContext(window),v=S.viewModel(c,S.parseRoute(location.hash));
              return {id:v.answer.id,gain:v.answer.gainText,sourceGain:c.ideas.recommendations[0].ourGain};}""")
            assert view["id"] == full[0]["id"] and view["sourceGain"] == baseline["gains"][0]
            assert full[0]["gain"] == "You gain " + view["gain"]
            assert page.evaluate(SAVED) == before
            dimensions = page.evaluate("({w:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})")
            assert dimensions["scroll"] <= dimensions["w"], dimensions
            text = page.inner_text("#v2Simplified")
            assert "They may take it" not in text and "Likely" not in text and "Possible" not in text
            page.screenshot(path=str(evidence / f"simplified-{width}.png"), full_page=True)
            first = page.locator("#v2Simplified [data-detail-for]").first
            for repeat in range(3):
                first.click()
                page.wait_for_selector("#ssDetailTitle")
                assert page.locator("#v2Simplified .v2-readout-view").count() == 6
                assert page.evaluate("document.activeElement.id") == "ssDetailTitle"
                dimensions = page.evaluate("({w:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})")
                assert dimensions["scroll"] <= dimensions["w"], dimensions
                toggle = page.locator("#v2Simplified .v2-lineup-bench-toggle").first
                toggle.click()
                assert toggle.get_attribute("aria-expanded") == "true"
                toggle.click()
                assert toggle.get_attribute("aria-expanded") == "false"
                if width == 320 and repeat == 0:
                    page.screenshot(path=str(evidence / "detail-320.png"), full_page=True)
                page.go_back()
                page.wait_for_selector("#v2Simplified[data-view=section]")
                assert page.evaluate("document.activeElement.dataset.detailFor") == view["id"]
                assert page.evaluate(SAVED) == before
            more = page.get_by_role("button", name="Show 10 more trades", exact=True)
            for _ in range(3):
                if more.is_visible():
                    count = page.locator(".ss-more li").count()
                    more.click()
                    assert page.locator(".ss-more li").count() == min(count + 10, baseline["count"] - 1)
            assert page.evaluate(SAVED) == before
            report["widths"].append({"width": width, "fullSimplifiedParity": True, "backRepeats": 3,
                                     "benchRepeats": 3, "moreRepeats": 3, "workspaceUnchanged": True, "overflow": False})

        # Negative fault injection never fabricates a recommendation: each path must clear a previous real answer.
        states = page.evaluate("""() => {
          const S=TradeValueSimplifiedSite,box=document.getElementById('v2Simplified'),ui=TradeValueLeague.ui;
          ui.running=true;S.activate(box);const loading=box.dataset.state;ui.running=false;
          const provider=window.TradeValueTradeIdeas;window.TradeValueTradeIdeas=undefined;S.activate(box);
          const incomplete=box.dataset.state;window.TradeValueTradeIdeas=provider;
          const compute=provider.compute;provider.compute=()=>{throw Error('controlled read failure')};S.activate(box);
          const error=box.dataset.state;provider.compute=compute;S.activate(box);
          return {loading,incomplete,error,restored:box.dataset.state};}""")
        assert states == {"loading": "loading", "incomplete": "incomplete", "error": "error", "restored": "answer"}, states
        report["states"].append({"controlledNegativePaths": states})
        page.evaluate("""() => {const M=TradeValueManagerProfiles,ws=TradeValueWorkspace.store.get();
          window.__reviewBook=M.store.get();M.store.update(book=>ws.teams.filter(t=>t.id!==ws.myTeamId)
            .reduce((next,t)=>M.ops.setExcluded(next,ws,t.id,true),book));}""")
        page.wait_for_selector("#v2Simplified[data-state=none]", timeout=120000)
        assert page.locator(".ss-offer").count() == 0
        report["states"].append("none: actual manager exclusions, no mocked recommendations")
        page.evaluate("TradeValueManagerProfiles.store.update(()=>window.__reviewBook)")
        page.wait_for_selector("#v2Simplified[data-state=answer]", timeout=120000)
        assert page.evaluate(SAVED) == before
        page.wait_for_timeout(1500)
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#v2Simplified[data-state=answer]", timeout=180000)
        assert page.evaluate(SAVED) == before
        report["reloadPreservedWorkspace"] = True
        assert report["pageErrors"] == [], report["pageErrors"]
        report["manifest"] = json.loads((site / "review-manifest.json").read_text())
    (evidence / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.site.resolve(), args.evidence.resolve()), indent=2))
