/* waivers.html: available players and your best adds on the live engine (JEG-1539, lane "find").
 *
 * The list the reader enters lives in DDF.state 'available' = {source:'list', players:[{n, pos}]} (sessionStorage
 * ddf:available; ddf:waivers is the "See waiver pickups" switch). Without an entered list the page uses the league's
 * available players (DDF.league: a chat link's list, or every priced player on no roster).
 * Best adds are TradeValueWaivers.evaluateAll for your roster (DDF.find.pickups), the live Waivers tab's evaluation.
 * Add from waivers (board S12-C): confirm a move from Waivers to your team; moves are kept in DDF.state 'moves'
 * ([{add, drop, at}], this browser only, never sent to your league provider). Undo removes the last one.
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (t) { return String(t).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var BUILD = "build.html";
  var SOURCE_WORD = {link: "From your chat", pasted: "Pasted", saved: "Saved league"};
  var W = {players: []}, TABLE = null, pending = null, lastOut = null;

  function load() {
    var saved = null;
    try { saved = DDF.state.get("available", null); } catch (e) { saved = null; }
    W.players = saved && Array.isArray(saved.players) ? saved.players.filter(function (p) { return p && typeof p.n === "string"; }).map(function (p) { return {n: p.n, pos: p.pos || ""}; }) : [];
  }
  function save() { try { DDF.state.set("available", {source: "list", players: W.players}); } catch (e) { /* this visit only */ } }
  function moves() { var m = DDF.state ? DDF.state.get("moves", []) : []; return Array.isArray(m) ? m : []; }
  function setMoves(list) {
    if (DDF.league && DDF.league.setMoves) DDF.league.setMoves(list);
    else { DDF.state.set("moves", list); if (DDF.league && DDF.league.refresh) DDF.league.refresh(); }
  }
  function myTeam() { return DDF.league && DDF.league.current() ? DDF.league.myTeam() : null; }
  function rosterNames() { var me = myTeam(); return me ? me.players.map(function (p) { return p.unpriced ? p.name : p.n; }) : []; }

  function fillContext(cur) {
    var span = document.querySelector(".ctx-strip > span:first-child");
    if (!span) return;
    if (!cur) { span.textContent = "No league yet"; return; }
    var label = DDF.link && DDF.link.settingsLabel ? DDF.link.settingsLabel(cur.settings) : "";
    span.textContent = "My league · " + (SOURCE_WORD[cur.source] || "Your league") + (label ? " · " + label : "");
  }
  // The candidates the best adds are judged on: the entered list (names matched to engine rows), else the league's.
  function candidates(cur) {
    if (W.players.length) {
      var recs = DDF.engine.players(), rows = recs.map(function (r) { return r.row; });
      var byRow = new Map(recs.map(function (r) { return [r.row, r]; }));
      var m = window.TradeValueFinder.matchNames(W.players.map(function (p) { return {name: p.n, pos: p.pos}; }), rows);
      return {source: "list", entries: m.matched.map(function (row) { var r = byRow.get(row); return {key: r.key, name: r.n, pos: r.pos, team: r.team}; })};
    }
    if (!cur) return {source: null, entries: []};
    return {source: cur.waiversFromLink ? "link" : "league", entries: cur.waivers.map(function (r) { return {key: r.key, name: r.n, pos: r.pos, team: r.team}; })};
  }

  function render() {
    var cur = DDF.league ? DDF.league.current() : null, me = myTeam();
    fillContext(cur);
    var cand = candidates(cur), n = W.players.length;
    $("status-title").textContent = n ? n + " available player" + (n === 1 ? "" : "s") + " entered"
      : cand.entries.length ? cand.entries.length + " available players in your league" : "No available players entered";
    $("status-source").textContent = n ? "Your best adds are judged on this list." : cand.source === "link" ? "From your chat link." : cand.source === "league" ? "Everyone with a value who is on no roster in your league. Paste your league site's list to use it instead." : "";
    var roster = rosterNames().length;
    $("roster-line").innerHTML = !cur ? 'Your league is not entered yet · <a href="connect.html">add it on Paste my league</a>'
      : me ? "Your roster: " + roster + ' players · <a href="connect.html">edit on Paste my league</a>' : 'Your team is not confirmed yet · <a href="setup.html">confirm your team</a>';
    $("list").innerHTML = W.players.map(function (p, i) { return "<li>" + esc(p.n) + (p.pos ? " <small>" + esc(p.pos) + "</small>" : "") + '<button type="button" data-remove="' + i + '" aria-label="Remove ' + esc(p.n) + '">✕</button></li>'; }).join("");
    $("list").hidden = !n; $("list-empty").hidden = !!n || cand.entries.length > 0; $("list-tools").hidden = !n;
    $("howto").hidden = !!n; $("paste-step").textContent = n ? "01" : "02"; $("manual-step").textContent = n ? "02" : "03";
    $("entry-hint").textContent = n ? "Add more, or replace the list" : "Start here";
    renderAdds(cur, me, cand);
  }

  /* ---------- best adds ---------- */
  var gainOf = function (r) { return Math.round(r.starterDelta * 10) / 10; };
  function renderAdds(cur, me, cand) {
    var box = $("adds"), note = $("adds-note");
    $("adds-empty").innerHTML = !cur ? 'Your best adds need your league. <a href="connect.html">Paste my league</a>'
      : !me ? 'Your best adds need to know which team is yours. <a href="setup.html">Confirm your team</a>'
        : !cand.entries.length ? "Add the players available in your league below to see your best adds." : "";
    $("adds-empty").hidden = !$("adds-empty").innerHTML;
    var ctx = DDF.find.context();
    lastOut = cur && me && ctx && cand.entries.length ? DDF.find.pickups(ctx, DDF.find.entriesOf(me), cand.entries, "DDF") : null;
    var res = lastOut ? lastOut.results.filter(function (r) { return r.starterDelta !== null && gainOf(r) > 0; }) : [];
    res.sort(function (a, b) { return b.starterDelta - a.starterDelta || (b.totalDelta || 0) - (a.totalDelta || 0) || String(a.name).localeCompare(String(b.name)); });
    var min = +$("adds-min").value;
    var pass = res.filter(function (r) { return gainOf(r) >= min; }), below = res.length - pass.length;
    box.innerHTML = pass.map(function (r, i) {
      var drop = r.drop ? r.drop.name : null;
      var href = BUILD + "?mode=league&waivers=1" + (drop ? "&drop=" + encodeURIComponent(drop) : "") + "&add=" + encodeURIComponent(r.name);
      return '<li class="wa-card' + (i === 0 ? " is-best" : "") + '" data-pickup data-pickup-gain="' + gainOf(r) + '" data-add="' + esc(r.candidate.player_key) + '" data-drop="' + esc(r.drop ? r.drop.player_key : "") + '">'
        + '<div class="wa-main">' + (i === 0 ? '<span class="wa-best">Best add</span>' : "") + '<p class="wa-move"><span><small>You add</small><b>' + esc(r.name) + " · " + esc(r.pos) + "</b></span>"
        + "<span><small>You drop</small><b>" + esc(drop || "Nobody (open roster spot)") + "</b></span></p>"
        + '<p class="wa-meta">' + esc(r.verdict) + " · with bench " + DDF.find.shown(r.totalDelta) + "</p></div>"
        + '<div class="wa-gain"><small>Your starters (DDF)</small><b>' + DDF.find.shown(r.starterDelta) + "</b></div>"
        + '<div class="wa-act"><button type="button" data-add-move="' + i + '">Add to my team</button><a class="button" href="' + esc(href) + '">Evaluate pickup</a></div></li>';
    }).join("");
    box.hidden = !pass.length;
    box._list = pass;
    note.textContent = !lastOut ? "" : !res.length ? "No available player improves your starters right now."
      : below ? below + (below === 1 ? " more add sits" : " more adds sit") + " below the " + min + "-point bar. Lower the minimum gain to see " + (below === 1 ? "it" : "them") + "." : "";
    var mv = moves();
    $("undo-move").hidden = !mv.length;
    $("moves-line").textContent = mv.length ? mv.length + (mv.length === 1 ? " roster move" : " roster moves") + " kept in this browser." : "";
  }
  function askMove(r) {
    pending = {add: String(r.candidate.player_key), drop: r.drop ? String(r.drop.player_key) : null, name: r.name, dropName: r.drop ? r.drop.name : null};
    $("confirm-text").textContent = "Move " + r.name + " from Waivers to My team" + (pending.dropName ? ", and " + pending.dropName + " to Waivers" : "") + "?";
    $("confirm-move").hidden = false;
    $("confirm-yes").focus();
  }
  function confirmMove() {
    if (!pending) return;
    var list = moves().concat([{add: pending.add, drop: pending.drop, at: Date.now()}]);
    var done = pending.name;
    pending = null;
    $("confirm-move").hidden = true;
    setMoves(list);
    W.players = W.players.filter(function (p) { return p.n !== done; });
    save();
    render();
    $("moves-status").textContent = done + " moved to your team.";
  }

  /* ---------- entry (paste / add one) ---------- */
  async function playerTable() {
    if (TABLE) return TABLE;
    try {
      var rows = await (await fetch("players-table-1.json")).json();
      TABLE = rows.map(function (r) { var parts = String(r).split("|"); return {n: (parts[0] || "").trim(), pos: (parts[1] || "").trim()}; })
        .filter(function (p) { return p.n.length >= 5; }).sort(function (a, b) { return b.n.length - a.n.length; });
    } catch (e) { TABLE = []; }
    $("all-players").innerHTML = TABLE.slice().sort(function (a, b) { return a.n.localeCompare(b.n); }).map(function (p) { return '<option value="' + esc(p.n) + '">'; }).join("");
    return TABLE;
  }
  // "Name · POS" lines, otherwise known player names found in messy site text (the same rules as build.html).
  function parseAvailable(text, table) {
    var found = new Map(), skipped = 0;
    var norm = function (p) { p = (p || "").toUpperCase(); return p === "D/ST" ? "DEF" : p; };
    var add = function (n, pos) { n = n.trim(); if (n && !found.has(n)) found.set(n, {n: n, pos: norm(pos) || ((table.find(function (t) { return t.n === n; }) || {}).pos || "")}); };
    String(text).split(/\r?\n/).forEach(function (raw) {
      var line = raw.trim(); if (!line) return;
      var m = /^([A-Za-z][A-Za-z.'’\- ]+?)\s*(?:·|,|\||\t| - | – )\s*(QB|RB|WR|TE|K|DEF|D\/ST)\b/i.exec(line);
      if (m) { add(m[1], m[2]); return; }
      var rest = line, hit = false;
      table.forEach(function (p) { if (rest.indexOf(p.n) >= 0) { add(p.n, p.pos); rest = rest.split(p.n).join(" | "); hit = true; } });
      if (!hit && /^[A-Z][A-Za-z.'’\-]+(?: [A-Z][A-Za-z.'’\-]+){1,3}$/.test(line)) { add(line, ""); hit = true; }
      if (!hit) skipped++;
    });
    return {players: Array.from(found.values()), skipped: skipped};
  }
  function merge(list) {
    var mine = new Set(rosterNames()), have = new Set(W.players.map(function (p) { return p.n; }));
    var fresh = list.filter(function (p) { return !mine.has(p.n) && !have.has(p.n); });
    W.players = W.players.concat(fresh); save(); render();
    return {added: fresh.length, onRoster: list.filter(function (p) { return mine.has(p.n); }).length, dupes: list.filter(function (p) { return have.has(p.n); }).length};
  }

  function wire() {
    $("paste-add").onclick = async function () {
      var text = $("pool").value;
      if (!text.trim()) { $("paste-status").textContent = "Paste or type at least one player."; return; }
      var parsed = parseAvailable(text, await playerTable()), r = merge(parsed.players);
      $("paste-status").textContent = (r.added ? r.added + " player" + (r.added === 1 ? "" : "s") + " added" : "No new players found") + (r.dupes ? ", " + r.dupes + " already in the list" : "")
        + (r.onRoster ? ", " + r.onRoster + " on your roster left out" : "") + (parsed.skipped ? ", " + parsed.skipped + " line" + (parsed.skipped === 1 ? "" : "s") + " skipped" : "") + ".";
      if (r.added) $("pool").value = "";
    };
    $("manual-add").onclick = async function () {
      var n = $("manual-name").value.trim();
      if (!n) { $("manual-status").textContent = "Type a player name first."; $("manual-name").focus(); return; }
      var table = await playerTable(), known = table.find(function (p) { return p.n.toLowerCase() === n.toLowerCase(); });
      var r = merge([{n: known ? known.n : n, pos: $("manual-pos").value || (known ? known.pos : "")}]);
      $("manual-status").textContent = r.added ? (known ? known.n : n) + " added." : r.onRoster ? n + " is on your roster, so it was left out." : n + " is already in the list.";
      if (r.added) { $("manual-name").value = ""; $("manual-pos").value = ""; $("manual-name").focus(); }
    };
    $("manual-name").addEventListener("focus", playerTable, {once: true});
    $("list").onclick = function (e) {
      var b = e.target.closest("[data-remove]"); if (!b) return;
      var p = W.players[+b.dataset.remove];
      W.players.splice(+b.dataset.remove, 1); save(); render();
      $("list-status").textContent = p.n + " removed.";
      ($("list").querySelector("button") || $("pool")).focus();
    };
    $("clear-list").onclick = function () {
      var n = W.players.length; W.players = []; save(); render();
      $("list-status").textContent = "List cleared: " + n + " player" + (n === 1 ? "" : "s") + " removed.";
      $("entry").open = true; $("pool").focus();
    };
    $("adds-min").addEventListener("change", render);
    $("adds").addEventListener("click", function (e) {
      var b = e.target.closest("[data-add-move]"); if (!b) return;
      var r = $("adds")._list[+b.dataset.addMove]; if (r) askMove(r);
    });
    $("confirm-no").onclick = function () { pending = null; $("confirm-move").hidden = true; $("moves-status").textContent = "Move cancelled."; };
    $("confirm-yes").onclick = confirmMove;
    $("undo-move").onclick = function () {
      var list = moves(); if (!list.length) return;
      list.pop(); setMoves(list); render();
      $("moves-status").textContent = "Last move undone.";
    };
    document.querySelectorAll("[data-provider]").forEach(function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll("[data-provider]").forEach(function (o) { var on = o === b; o.setAttribute("aria-pressed", String(on)); o.classList.toggle("selected", on); });
        document.querySelectorAll("[data-walkthrough]").forEach(function (w) { w.hidden = w.dataset.walkthrough !== b.dataset.provider; });
      });
    });
  }

  function start() {
    if (location.hash === "#after") { location.replace("find.html"); return; }
    load();
    wire();
    $("entry").open = !W.players.length || location.hash === "#entry";
    Promise.all([DDF.engine.ready, DDF.league.ready]).then(function () {
      render();
      $("entry").open = (!W.players.length && !(DDF.league.current() && DDF.league.current().waivers.length)) || location.hash === "#entry";
      DDF.league.on(function () { render(); });
    }).catch(function (e) { console.error(e); $("adds-note").textContent = "The values did not load. Reload the page to try again."; });
  }
  DDF.waiversPage = {render: render, last: function () { return lastOut; }};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
