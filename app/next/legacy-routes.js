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

  /* ---- links that carry a league (rosters), not just a route ----
   * The v2 assistant links (ddf-assist.js, chat site_url: #find-trade / #compare-trade / #trade-targets with mine=,
   * theirs=, target=) and the league finder's share link (#find-league?workspace=<teams>&wm=<mine>) carry rosters the
   * redesigned pages read only as a league. They become a redesign chat link (LINK-FORMAT state through DDF.link.encode,
   * #s=<token>) on the page that does the job: the rosters are the league (mine = your team, theirs = one other team),
   * the link's scoring / teams / roster are its settings, give/get ride to Build a Trade. Not carried: a carried trade
   * (tc), the league finder's filters (size, fit, opp, mcap, mch, trade) and settings beyond the six lineup slots. */
  var STATE_KEYS = ["mine", "theirs", "target", "workspace"];
  var STATE_ROUTES = {"#compare-trade": "build", "#find-trade": "recommendations", "#find-league": "recommendations",
    "#trade-targets": "values"};
  var TEAMS_ALLOWED = [8, 10, 12, 14];
  var SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "BENCH"];

  function stateLink(hash) {
    var parts = String(hash || "").split("?"), base = canonical(parts[0]);
    var query = parts.slice(1).join("&");
    if (!query) return null;
    var params = new URLSearchParams(query);
    if (base === "#find-trade" && params.has("workspace")) base = "#find-league";
    if (!STATE_ROUTES[base] || !STATE_KEYS.some(function (k) { return params.has(k); })) return null;
    return {base: base, view: STATE_ROUTES[base], query: query, params: params};
  }

  function nearestTeams(n) {
    if (!isFinite(n)) return null;
    return TEAMS_ALLOWED.reduce(function (best, t) { return Math.abs(t - n) < Math.abs(best - n) ? t : best; }, 12);
  }
  // The link's league settings in the LINK-FORMAT shape (settings are required there): the link's own, else the
  // reader's saved settings, else the engine's default lineup (league.ts DEFAULT_ROSTER).
  function linkSettings(league) {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem("ddf.v2.league-settings") || "null"); } catch (e) { saved = null; }
    var src = league && league.scoring ? league : (saved && saved.scoring ? saved : null);
    var roster = (src && src.roster) || {};
    var fallback = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, BENCH: 7};
    var slots = SLOT_ORDER.map(function (k) { var n = Number(roster[k]); return Number.isInteger(n) && n >= 0 && n <= 20 ? n : fallback[k]; });
    return {scoring: (src && src.scoring) || "ppr", teams: nearestTeams(Number(src && src.teams)) || 12,
      superflex: Number(roster.SUPERFLEX) > 0, slots: slots};
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src; s.onload = resolve; s.onerror = function () { reject(new Error("could not load " + src)); };
      document.head.appendChild(s);
    });
  }

  // -> Promise of the URL to open (a #s= link on the view's page), or null when the link cannot be read.
  function translate(link, root) {
    var need = [];
    if (!window.DDFState) need.push(loadScript(new URL("v2/ddf-state.js", root).href));
    if (link.base === "#find-league" && !window.TradeValueWorkspace) need.push(loadScript(new URL("v2/workspace.js", root).href));
    // The front door loads site.js itself at the end of <body>; loaded here only when a page has none.
    var parsed = document.readyState === "loading"
      ? new Promise(function (r) { document.addEventListener("DOMContentLoaded", r); }) : Promise.resolve();
    need.push(parsed.then(function () {
      if (!(window.DDF && window.DDF.link && window.DDF.link.encode)) return loadScript(new URL("site.js", root).href);
    }));
    var table = fetch(new URL("players-table-1.json", root).href).then(function (r) { return r.json(); });
    return Promise.all([table].concat(need)).then(function (got) {
      var rows = got[0];
      var byKey = new Map(), idOf = new Map();
      rows.forEach(function (row, i) {
        var f = String(row).split("|");
        byKey.set(f[3], {name: f[0], pos: f[1], team: f[2]});
        idOf.set(f[3], i);
      });
      // A player for a LINK-FORMAT list: its table id, else its name; a defense or kicker key (x:POS:..) has neither.
      var entry = function (p) {
        if (!p) return null;
        if (p.key !== undefined && idOf.has(String(p.key))) return idOf.get(String(p.key));
        if (p.name && !/^Player \d+$/.test(p.name)) return p.name;
        return null;
      };
      var list = function (l) { return (l || []).map(entry).filter(function (x) { return x !== null; }); };
      var decoded = window.DDFState.decodeQuery(link.query).state || {};
      var work = decoded.work || {};
      var st = {v: 1, view: link.view, settings: linkSettings(decoded.league), table: 1, teams: [], me: 0};
      if (link.base === "#find-league") {
        var teams = window.TradeValueWorkspace.decodeShare(link.params.get("workspace"), byKey);
        if (!teams.length) return null;
        st.teams = teams.map(function (t) { return {name: t.name, players: list(t.entries)}; });
        var wm = Number(link.params.get("wm"));
        st.me = Number.isInteger(wm) && st.teams[wm] ? wm : null;
      } else {
        st.teams.push({name: "Your team", players: list(work.mine)});
        if (work.theirs && work.theirs.length) st.teams.push({name: "Their team", players: list(work.theirs)});
        if (work.target) { var t = entry(work.target); if (t !== null) st.target = t; }
        if (work.give || work.get) st.trade = {give: list(work.give), get: list(work.get), partner: st.teams.length > 1 ? 1 : null};
      }
      var page = window.DDF.link.pageFor(link.view);
      if (link.view === "build" && st.trade) {
        var q = new URLSearchParams();
        (work.give || []).forEach(function (p) { var n = entry(p); if (typeof n === "number") n = rows[n].split("|")[0]; if (n !== null) q.append("give", n); });
        (work.get || []).forEach(function (p) { var n = entry(p); if (typeof n === "number") n = rows[n].split("|")[0]; if (n !== null) q.append("get", n); });
        if (q.toString()) page += "?" + q.toString();
      }
      return window.DDF.link.encode(st, {page: page, base: root}).then(function (url) {
        return link.view === "values" ? url + "&buy-sell" : url;
      });
    });
  }

  window.DDFLegacyRoutes = {resolve: resolve, ROUTES: ROUTES, stateLink: stateLink, translate: translate};
  if (document.documentElement.hasAttribute("data-legacy-routes-off")) return;
  var atRoot = !document.documentElement.hasAttribute("data-legacy-stub");
  var root = here();
  var carried = stateLink(location.hash);
  if (carried && !atRoot) {
    // The /v2/ stub hands a league link to the front door, which reads it (site.js and the player table live there).
    try { location.replace(new URL("./", root).href + location.hash); } catch (e) { /* stays */ }
    return;
  }
  if (carried) {
    // Hidden until the link is read, so the front door does not flash; any failure falls back to the plain route.
    var html = document.documentElement;
    html.style.visibility = "hidden";
    var done = false;   // the first redirect wins (a late translate() after the timeout does not redirect again)
    var fallback = function () {
      if (done) return;
      done = true;
      html.style.visibility = "";
      var plain = resolve(location.hash, {atRoot: atRoot, root: root});
      if (plain && plain !== location.href) { try { location.replace(plain); } catch (e) { /* stays */ } }
    };
    var timer = setTimeout(fallback, 15000);
    translate(carried, root).then(function (url) {
      clearTimeout(timer);
      if (!url) return fallback();
      if (done) return;
      done = true;
      location.replace(url);
    }, function (e) { clearTimeout(timer); console.warn(e); fallback(); });
    return;
  }
  var target = resolve(location.hash, {atRoot: atRoot, root: root});
  if (target && target !== location.href) {
    try { location.replace(target); } catch (e) { /* the page stays; its links still work */ }
  }
})();
