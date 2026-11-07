/* Old v2 hash routes -> the redesigned pages (JEG-1539, plan step 5 of JEG-1534).
 *
 * The v2 shell no longer runs at the site root or at /v2/. This file runs first in the <head> of the new front door
 * (index.html) and of the /v2/ stub, so every link that was ever shared (chat site_url links, bookmarks, the v2 nav)
 * lands on the page that does that job now. location.replace, so Back skips the old address.
 *
 * Same rules as v2.js SWAPPED_ROUTES (steps 1-4): an exact key wins over a "#base/*" key, and the route's query rides
 * along after the target's own hash ("values.html#?valuecontext=1&basis=..", "build.html#?give=..&get=..") so a
 * shared value context or trade still applies. Targets resolve against this script's own folder (the site root).
 *
 * window.DDFLegacyRoutes.resolve(hash, {atRoot}) -> target URL (string) or null to stay; tests call it directly.
 */
(function () {
  "use strict";
  var ROUTES = {
    "#player-values": "values.html",
    "#value-overrides": "values.html#overrides",
    "#risers-fallers": "values.html",
    "#trade-targets": "values.html#buy-sell",
    "#compare-trade": "build.html",
    "#find-trade": "find.html",
    "#find-league": "find.html",
    "#waivers": "waivers.html",
    "#simplified-site": "index.html",        // JEG-1263 Simplified site, retired at step 5
    "#simplified-site/*": "index.html",
    "#writing/manifesto": "learn.html#manifesto",
    "#writing/how-values": "learn.html#numbers/logic",
    "#writing/*": "learn.html",
    "#values-auditing/health-check": "learn.html#numbers/pie",
    "#values-auditing/single-source": "learn.html#numbers/build-up",
    "#values-auditing/*": "learn.html#numbers/pie"
  };
  // Older spellings v2.js still accepted (LEGACY_ROUTES and the #research/ prefix).
  var ALIASES = {"#manifesto": "#writing/manifesto", "#how-values": "#writing/how-values", "#research": "#writing/research",
    "#values-auditing/value-pie": "#values-auditing/health-check"};

  function canonical(base) {
    if (ALIASES[base]) return ALIASES[base];
    if (base.indexOf("#research/") === 0) return "#writing/" + base.slice(1);
    return base;
  }
  function routeFor(base) {
    if (Object.prototype.hasOwnProperty.call(ROUTES, base)) return ROUTES[base];
    var best = null;
    Object.keys(ROUTES).forEach(function (key) {
      if (key.slice(-2) !== "/*") return;
      var stem = key.slice(0, -2);
      if ((base === stem || base.indexOf(stem + "/") === 0) && (!best || key.length > best.length)) best = key;
    });
    return best ? ROUTES[best] : null;
  }
  function here() {
    var s = document.currentScript && document.currentScript.src;
    return s ? new URL(".", s).href : new URL(".", location.href).href;
  }

  function resolve(hash, opts) {
    opts = opts || {};
    var atRoot = opts.atRoot !== false;
    var root = opts.root || here();
    hash = hash || "";
    // A redesign chat link (#s=...) opens on the entry page, which reads the token and routes to its view.
    if (/^#s=/.test(hash)) return new URL("connect.html", root).href + hash;
    var parts = hash.split("?"), base = canonical(parts[0]), query = parts.slice(1);
    // JEG-1094: a league share link on #find-trade belongs to the league-wide screen.
    if (base === "#find-trade" && /^workspace=/.test(query[0] || "")) base = "#find-league";
    var target = base && base !== "#" && base !== "#home" ? routeFor(base) : null;
    if (!target) return atRoot ? null : new URL("./", root).href;   // the home page; an unknown hash stays on it
    if (target === "index.html") return new URL("./", root).href;
    var rest = query.length ? "?" + query.join("?") : "";
    return new URL(target.indexOf("#") >= 0 || !rest ? target : target + "#", root).href + rest;
  }

  window.DDFLegacyRoutes = {resolve: resolve, ROUTES: ROUTES};
  if (document.documentElement.hasAttribute("data-legacy-routes-off")) return;
  var atRoot = !document.documentElement.hasAttribute("data-legacy-stub");
  var target = resolve(location.hash, {atRoot: atRoot});
  if (target && target !== location.href) {
    try { location.replace(target); } catch (e) { /* the page stays; its links still work */ }
  }
})();
