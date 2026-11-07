/* setup.html, "Which team is yours?" (JEG-1538): the teams come from the league kept on connect.html.
 *
 * Source, in order: sessionStorage ddf:pasted (a paste or manual entry, connect-entry.js) or the league carried from a
 * chat link (DDF.link.current().teams). Neither: the page says no rosters were added and links back to connect.html.
 * Confirming a team stores it as `me` (ddf:pasted.me, or DDF.link.update({me}) for a chat league).
 *
 * Storage bridge (plan D4, until JEG-1539 retires the live league pages): when the reader confirms a team, the pasted
 * league is also written to localStorage ddf.v2.workspaces in the live workspace format (workspace.js
 * normalizeWorkspace reads it), so the live Find a trade and league pages show the same league. The live store holds
 * one league. A league this tab wrote (its id is in sessionStorage ddf:bridgedWs) is updated in place, keeping its team
 * ids; any other saved league with teams is replaced only after the reader says so ("Replace it"), never silently.
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
  function readStore() {
    try { var d = JSON.parse(localStorage.getItem(WS_KEY) || "null"); return d && d.v === 1 && Array.isArray(d.workspaces) ? d : null; }
    catch (e) { return null; }
  }
  /* the pasted league into the live store: 'written', 'ask' (another saved league is there) or 'failed' */
  function bridge(rec, opts) {
    try {
      var now = Date.now(), old = readStore();
      var prev = old ? (old.workspaces.filter(function (w) { return w && w.id === old.activeId; })[0] || old.workspaces[0]) : null;
      var ours = !!(prev && prev.id && prev.id === DDF.state.get("bridgedWs", null));
      var occupied = !!(prev && ((Array.isArray(prev.teams) && prev.teams.length) || prev.settings));
      if (occupied && !ours && !(opts && opts.replace)) return "ask";
      var oldTeams = ours && Array.isArray(prev.teams) ? prev.teams : [];
      var teams = rec.teams.slice(0, 20).map(function (t, i) {
        var entries = (t.players || []).filter(function (p) { return p && p.key; }).map(function (p) {
          var e = {key: String(p.key), name: String(p.name), pos: String(p.pos || "")};
          if (p.team) e.team = String(p.team);
          if (p.slot) e.slot = String(p.slot);
          return e;
        }).concat((t.unmatched || []).filter(function (u) { return u.reason === "kdef" && u.key; }).map(function (u) {
          var e = {key: String(u.key), name: String(u.line), pos: String(u.pos || "")};
          if (u.team) e.team = String(u.team);
          return e;
        }));
        var unresolved = (t.unmatched || []).filter(function (u) { return u.reason !== "kdef"; }).length;
        var same = oldTeams[i] && oldTeams[i].name === String(t.name).slice(0, 40) ? oldTeams[i] : null;
        return {id: same ? same.id : newId("team"), name: String(t.name).slice(0, 40), sourceText: "", sourceTeam: null, removed: [], entries: entries,
          createdAt: same ? same.createdAt : now, updatedAt: now,
          provenance: rec.source === "paste" ? {unresolved: unresolved, observedAt: now, editedAt: null} : {unresolved: 0, editedAt: now}};
      });
      var mine = Number.isInteger(rec.me) && teams[rec.me] ? teams[rec.me].id : null;
      var ws = ours ? Object.assign({}, prev) : {id: newId("league"), name: "My league", settings: null, createdAt: now};
      ws.teams = teams; ws.myTeamId = mine; ws.updatedAt = now;
      /* JEG-1564: the league's name, roster date and (this device only) league ID */
      ws.name = rec.name || "My league";
      if (rec.enteredAt) ws.enteredAt = rec.enteredAt;
      if (rec.leagueId) ws.leagueId = String(rec.leagueId); else delete ws.leagueId;
      localStorage.setItem(WS_KEY, JSON.stringify({v: 1, workspaces: [ws], activeId: ws.id}));
      DDF.state.set("bridgedWs", ws.id);
      return "written";
    } catch (e) { return "failed"; }
  }
  function offerReplace(rec) {
    var box = document.getElementById("bridge-ask");
    if (!box) return;
    box.hidden = false;
    document.getElementById("bridge-replace").onclick = function () {
      var r = bridge(rec, {replace: true});
      document.getElementById("bridge-status").textContent = r === "written" ? "Done. Find a trade now uses these rosters." : "That did not save. Try again.";
      if (r === "written") { document.getElementById("bridge-replace").hidden = true; document.getElementById("bridge-keep").hidden = true; }
    };
    document.getElementById("bridge-keep").onclick = function () {
      box.hidden = true;
      DDF.state.set("bridgeKeep", true);
    };
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
    /* "Name this league" (JEG-1564): the saved name, else the name found in the paste as a suggestion, else empty
       ("My league" is the default). Saved only when the reader edits it or presses Next, never on its own. */
    var nameBox = document.getElementById("setup-name-box"), nameIn = document.getElementById("league-name"), note = document.getElementById("league-name-note");
    var curLink = null; try { curLink = DDF.link && DDF.link.current && DDF.link.current(); } catch (e) { curLink = null; }
    var savedName = src.kind === "pasted" ? src.rec.name : curLink && curLink.name;
    var suggested = src.kind === "pasted" ? src.rec.suggestedName : null;
    if (nameBox && nameIn) {
      nameBox.hidden = false;
      nameIn.value = savedName || suggested || "";
      note.textContent = savedName ? "Used in your bookmark and page titles." : suggested
        ? "We found this name in your paste" + (src.rec.leagueId ? " (ID# " + src.rec.leagueId + ")" : "") + ". Keep it or change it."
        : "Used in your bookmark and page titles. Leave it empty to use \u201cMy league\u201d.";
    }
    function saveName() {
      if (!nameIn) return;
      var v = Array.from(nameIn.value.replace(/\s+/g, " ").trim()).slice(0, 40).join("").trim() || null;
      if (src.kind === "pasted") { src.rec.name = v; DDF.state.set("pasted", src.rec); if (Number.isInteger(src.rec.me) && DDF.state.get("bridgedWs", null)) bridge(src.rec); }
      else if (DDF.link && DDF.link.update) { try { var cur = DDF.link.current(); if (cur) { DDF.link.update({name: v || undefined}); } } catch (e) { /* the name still shows */ } }
      if (DDF.leagueMeta) DDF.leagueMeta.refresh();
    }
    if (nameIn) nameIn.addEventListener("change", saveName);
    var nextBtns = [document.getElementById("continue-btn"), document.getElementById("continue-top")];
    nextBtns.forEach(function (b) { if (b) b.addEventListener("click", saveName, true); });
    /* Enter in the form must not submit it: at the root its action is a live hash route */
    form.addEventListener("submit", function (e) { e.preventDefault(); var b = document.getElementById("continue-btn"); if (b && b.getAttribute("href")) b.click(); });
    form.addEventListener("change", function (e) {
      var i = e.target && e.target.dataset ? e.target.dataset.i : undefined;
      if (i === undefined) return;
      i = Number(i);
      if (DDF.leagueMeta) DDF.leagueMeta.want("team", i + ":" + src.teams[i].name);
      if (src.kind === "pasted") {
        src.rec.me = i; DDF.state.set("pasted", src.rec);
        if (bridge(src.rec) === "ask" && !DDF.state.get("bridgeKeep", false)) offerReplace(src.rec);
      }
      else if (DDF.link && DDF.link.update) { try { DDF.link.update({me: i}); } catch (err) { /* the choice still shows */ } }
    });
  }
  if (document.getElementById("team-form")) init(); else document.addEventListener("DOMContentLoaded", init);
  DDF.setupEntry = {bridge: bridge, source: source};
})();
