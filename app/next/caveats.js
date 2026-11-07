/* DDF caveats note (reusable). Jeremy, 2026-11-07: tell users our caveats so they do not read the numbers as "act blindly".
 *
 * Usage: put <div data-ddf-caveats="assessment|recommendations|entry"></div> where the note belongs and load this script.
 *   assessment, recommendations: short note + a collapsed "What these numbers assume" list.
 *   entry: one line only (shown when a league first loads in the paste flow).
 * API: DDF.caveats.mount(el, variant) renders into any element. Add siblings (for example the opportunity-size read) with
 * the .ddf-caveats__slot container each note carries; it is empty and hidden until something is put in it.
 * Client-side only; no storage, no network.
 */
(function () {
  var DDF = window.DDF = window.DDF || {};
  var LEAD = {
    assessment: "These numbers are a starting point, not advice. Check them against your league before you act.",
    recommendations: "These are leads to check, not advice. Check each one against your league before you act.",
    entry: "Check these rosters against your league before you continue. They are as of your paste, and values are not advice."
  };
  var DETAILS = [
    ["Snapshot week", "Values come from one weekly snapshot. News since then is not in them."],
    ["Value above waivers", "A player is measured against the best player you could add from waivers, so a deep bench player can read low."],
    ["Estimated chart values", "Analyst charts (the average of CBS Sports, USA Today and FantasyPros) and Live market (FantasyCalc) are published numbers we put on one scale and adjust to your league settings. Where a chart does not list a player, we estimate one."],
    ["Your league settings", "We use the scoring, team count, Superflex and lineup you confirmed. Check them in your league settings."],
    ["Pasted rosters", "Rosters are as of your paste. If a trade or add happened since, add your league again."],
    ["Not advice", "Values show what the charts say, not what will happen. The decision is yours."]
  ];
  var CSS = ".ddf-caveats{margin:14px 0 18px;padding:12px 16px;background:#f4f6f2;border:1px solid #dbe0dc;border-left:3px solid #176c4d;border-radius:8px;max-width:72ch;font-size:15px;line-height:1.5;color:#142b25}" +
    ".ddf-caveats__lead{margin:0}.ddf-caveats--entry{font-size:14px;margin:12px 0}" +
    ".ddf-caveats details{margin:6px 0 0}.ddf-caveats summary{display:inline-flex;align-items:center;min-height:44px;cursor:pointer;color:#176c4d;font-weight:600;text-decoration:underline;text-underline-offset:4px}" +
    ".ddf-caveats ul{margin:4px 0 6px;padding-left:20px}.ddf-caveats li{margin:6px 0}.ddf-caveats__slot:empty{display:none}.ddf-caveats__slot{margin-top:8px}";
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function style() {
    if (document.getElementById("ddf-caveats-css")) return;
    var st = document.createElement("style"); st.id = "ddf-caveats-css"; st.textContent = CSS; document.head.appendChild(st);
  }
  function mount(el, variant) {
    variant = LEAD[variant] ? variant : "assessment";
    style();
    var html = '<p class="ddf-caveats__lead">' + esc(LEAD[variant]) + "</p>";
    if (variant !== "entry") {
      html += '<details class="ddf-caveats__more"><summary>What these numbers assume</summary><ul>' +
        DETAILS.map(function (d) { return "<li><strong>" + esc(d[0]) + ".</strong> " + esc(d[1]) + "</li>"; }).join("") + "</ul></details>";
    }
    html += '<div class="ddf-caveats__slot"></div>';
    el.className = (el.className ? el.className + " " : "") + "ddf-caveats ddf-caveats--" + variant;
    el.setAttribute("role", "note");
    el.setAttribute("aria-label", "Before you act");
    el.innerHTML = html;
  }
  DDF.caveats = {mount: mount, lead: LEAD, details: DETAILS};
  function run() { document.querySelectorAll("[data-ddf-caveats]").forEach(function (el) { mount(el, el.getAttribute("data-ddf-caveats")); }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
