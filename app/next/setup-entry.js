/* setup.html, "Which team is yours?" (JEG-1538): the teams come from the league kept on connect.html.
 *
 * Source, in order: sessionStorage ddf:pasted (a paste or manual entry, connect-entry.js) or the league carried from a
 * chat link (DDF.link.current().teams). Neither: the page says no rosters were added and links back to connect.html.
 * Confirming a team stores it as `me` (ddf:pasted.me, or DDF.link.update({me}) for a chat league).
 *
 * Storage bridge (plan D4, until JEG-1539 retires the live league pages): a pasted league with the confirmed team is
 * also written to localStorage ddf.v2.workspaces in the live workspace format (workspace.js normalizeWorkspace reads
 * it), so the live Find a trade and league pages show the same league. The live league's id, name, settings and view
 * choices are kept; its teams are replaced, as a new paste on the live League tab does.
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var WS_KEY = "ddf.v2.workspaces";
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); };

  function source() {
    var pasted = DDF.state.get("pasted", null);
    if (pasted && Array.isArray(pasted.teams) && pasted.teams.length > 1) {
      return {kind: "pasted", rec: pasted, me: Number.isInteger(pasted.me) && pasted.teams[pasted.me] ? pasted.me : -1,
        teams: pasted.teams.map(function (t) { return {name: t.name, count: Array.isArray(t.players) ? t.players.length : Number(t.players) || 0}; })};
    }
    var cur = null;
    try { cur = DDF.link && DDF.link.current && DDF.link.current(); } catch (e) { cur = null; }
    if (cur && Array.isArray(cur.teams) && cur.teams.length > 1) {
      return {kind: "link", me: Number.isInteger(cur.me) && cur.teams[cur.me] ? cur.me : -1,
        teams: cur.teams.map(function (t, i) { return {name: t.name || "Team " + (i + 1), count: Array.isArray(t.players) ? t.players.length : 0}; })};
    }
    return null;
  }

  function newId(prefix) {
    try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) { /* fall through */ }
    return prefix + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }
  /* the pasted league into the live store; returns true when written */
  function bridge(rec) {
    try {
      var now = Date.now(), old = null;
      try { old = JSON.parse(localStorage.getItem(WS_KEY) || "null"); } catch (e) { old = null; }
      var prev = old && old.v === 1 && Array.isArray(old.workspaces)
        ? (old.workspaces.filter(function (w) { return w && w.id === old.activeId; })[0] || old.workspaces[0]) : null;
      var teams = rec.teams.slice(0, 20).map(function (t) {
        var entries = (t.players || []).filter(function (p) { return p && p.key; }).map(function (p) {
          var e = {key: String(p.key), name: String(p.name), pos: String(p.pos || "")};
          if (p.team) e.team = String(p.team);
          if (p.slot) e.slot = String(p.slot);
          return e;
        });
        var unresolved = (t.unmatched || []).filter(function (u) { return u.reason !== "kdef"; }).length;
        return {id: newId("team"), name: String(t.name).slice(0, 40), sourceText: "", sourceTeam: null, removed: [], entries: entries,
          createdAt: now, updatedAt: now,
          provenance: rec.source === "paste" ? {unresolved: unresolved, observedAt: now, editedAt: null} : {unresolved: 0, editedAt: now}};
      });
      var mine = Number.isInteger(rec.me) && teams[rec.me] ? teams[rec.me].id : null;
      var ws = prev && typeof prev === "object" ? Object.assign({}, prev) : {id: newId("league"), name: "My league", settings: null, createdAt: now};
      ws.teams = teams; ws.myTeamId = mine; ws.updatedAt = now;
      localStorage.setItem(WS_KEY, JSON.stringify({v: 1, workspaces: [ws], activeId: ws.id}));
      return true;
    } catch (e) { return false; }
  }

  function init() {
    var form = document.getElementById("team-form");
    if (!form) return;
    var box = form.querySelector(".setup-options"), intro = document.querySelector(".setup-intro");
    var empty = document.getElementById("setup-empty"), src = source();
    if (!src) {
      box.innerHTML = "";
      form.querySelector(".setup-selection").hidden = true;
      if (empty) empty.hidden = false;
      if (intro) intro.textContent = "Add your league's rosters first, then confirm which team is yours.";
      return;
    }
    box.innerHTML = src.teams.map(function (t, i) {
      var sel = i === src.me;
      return '<label class="setup-option ddf-pop ddf-lift' + (sel ? " selected" : "") + '"><input type="radio" name="team" value="' + esc(t.name) + '" data-i="' + i + '" required' + (sel ? " checked" : "") + "><span><strong>" + esc(t.name) + "</strong>"
        + (t.count ? '<span class="player-count">' + t.count + " player" + (t.count === 1 ? "" : "s") + "</span>" : "")
        + '</span><span class="selection-check" aria-hidden="true">✓</span></label>';
    }).join("");
    if (intro) intro.textContent = "We found these " + src.teams.length + " teams in your " + (src.kind === "link" ? "league" : "paste") + ". Confirm the one you manage so we can show your roster.";
    var nb = document.getElementById("continue-btn");
    if (nb) nb.setAttribute("data-summary", src.me >= 0 ? "Team: " + src.teams[src.me].name : "Confirm your team");
    if (src.kind === "pasted" && src.me >= 0) bridge(src.rec);
    form.addEventListener("change", function (e) {
      var i = e.target && e.target.dataset ? e.target.dataset.i : undefined;
      if (i === undefined) return;
      i = Number(i);
      if (src.kind === "pasted") { src.rec.me = i; DDF.state.set("pasted", src.rec); bridge(src.rec); }
      else if (DDF.link && DDF.link.update) { try { DDF.link.update({me: i}); } catch (err) { /* the choice still shows */ } }
    });
  }
  if (document.getElementById("team-form")) init(); else document.addEventListener("DOMContentLoaded", init);
  DDF.setupEntry = {bridge: bridge, source: source};
})();
