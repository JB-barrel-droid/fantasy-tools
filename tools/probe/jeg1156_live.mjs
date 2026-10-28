// Temporary probe (JEG-1156): read the live Player values page and print whether DDF Value is filled.
import { chromium } from "playwright-core";
const base = "https://jb-barrel-droid.github.io/fantasy-tools/";
const browser = await chromium.launch();
for (const [w, h] of [[1366, 768], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e).slice(0, 200)));
  await page.goto(base + "#player-values", { waitUntil: "networkidle", timeout: 120000 });
  await page.waitForFunction(() => document.querySelectorAll("#v2Table tbody tr").length > 5, null, { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(3000);
  const r = await page.evaluate(() => {
    const t = s => (document.querySelector(s)?.innerText || "").replace(/\s+/g, " ").trim();
    const heads = [...document.querySelectorAll("#v2Table thead th")].map(th => th.innerText.replace(/\s+/g, " ").trim());
    const di = heads.findIndex(x => /DDF Value/i.test(x));
    const rows = [...document.querySelectorAll("#v2Table tbody tr")];
    const cell = (tr, i) => (tr.children[i]?.innerText || "").replace(/\s+/g, " ").trim();
    const filled = di < 0 ? null : rows.filter(tr => { const v = cell(tr, di); return v && v !== "—" && v !== "-"; }).length;
    return { build: document.querySelector('meta[name="trade-chart-build"]')?.content, freshness: t("#v2FreshnessLabel") || t(".v2-freshness-short"),
      freshnessAria: document.querySelector(".v2-freshness")?.getAttribute("aria-label"), tableMeta: t("#v2TableMeta"),
      headers: heads, ddfCol: di, rows: rows.length, ddfFilled: filled,
      first5: rows.slice(0, 5).map(tr => [cell(tr, 0), cell(tr, 1), di >= 0 ? cell(tr, di) : null]) };
  });
  console.log(`JEG1156-LIVE ${w}x${h}: ${JSON.stringify({ ...r, pageErrors: errors })}`);
  await page.close();
}
await browser.close();
