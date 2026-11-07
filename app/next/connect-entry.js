/* connect.html on the live engine (JEG-1538): read the pasted rosters, show what we read, keep the league for setup.
 *
 * - "Check my rosters" (or a paste) reads the box with DDF.leaguePaste (live roster-paste.js matcher on engine rows,
 *   team names from rosterparse.js) and fills "Here's what we read from your paste" from that result.
 * - A paste we cannot read shows a status line and the edit-names box: the reader types the team names and we read again.
 * - One team's page shows the existing "That looks like one team" notice.
 * - Manual entry: team names, then players found by name on the engine's player list.
 * - The league is kept in sessionStorage ddf:pasted (league-paste.js record(), setup.html adds `me`); a new paste or
 *   manual league clears a league carried from a chat link (DDF.link.clear()), so the two never mix.
 * - Device: the page shows phone or computer copy steps (html[data-device]); "On a phone" / "On a computer" switches.
 *   Detection is local only (media queries, then the user agent); when unsure, both versions show.
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var plural = function (n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); };

  /* ---------- device ---------- */
  function detectDevice() {
    try {
      var coarse = matchMedia("(pointer: coarse)").matches, narrow = matchMedia("(max-width: 760px)").matches;
      var phoneUa = /iPhone|iPod|Android.+Mobile|Windows Phone|Mobile Safari/i.test(navigator.userAgent || "");
      if (phoneUa || (coarse && narrow)) return "phone";
      if (!coarse) return "desktop";
    } catch (e) { /* unknown: show both */ }
    return "";
  }
  function setDevice(d) {
    if (d) document.documentElement.setAttribute("data-device", d); else document.documentElement.removeAttribute("data-device");
  }
  setDevice(detectDevice());
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-show-device]");
    if (b) { e.preventDefault(); setDevice(b.getAttribute("data-show-device")); }
  });

  /* ---------- engine rows and the player table ---------- */
  var rowsCache = null;
  function rows() {
    if (rowsCache) return rowsCache;
    var C = DDF.engine && DDF.engine.controls && DDF.engine.controls();
    if (!C || !C.getAllRows) return null;
    rowsCache = C.getAllRows().filter(function (r) { return r && r.name && r.player_key !== undefined && r.player_key !== null; })
      .map(function (r) { return {player_key: r.player_key, name: r.name, pos: r.pos || "", team: r.team || ""}; });
    return rowsCache;
  }
  function table() { try { return (DDF.link && DDF.link.table && DDF.link.table(1)) || []; } catch (e) { return []; } }
  function whenRows() {
    var r = rows();
    if (r) return Promise.resolve(r);
    if (!DDF.engine || !DDF.engine.ready) return Promise.reject(new Error("engine"));
    return DDF.engine.ready.then(function () { var x = rows(); if (!x) throw new Error("engine"); return x; });
  }

  /* ---------- the kept league ---------- */
  function save(record) {
    try { if (DDF.link && DDF.link.clear) DDF.link.clear(); } catch (e) { /* no chat league to clear */ }
    DDF.state.set("pasted", record);
    document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: record}));
  }
  function drop() {
    DDF.state.remove("pasted");
    document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: null}));
  }
  function kept() { var p = DDF.state.get("pasted", null); return p && Array.isArray(p.teams) ? p : null; }

  /* ---------- status line under the paste box ---------- */
  function status(text, kind) {
    var st = $("entry-status");
    if (!st) return;
    st.textContent = text || "";
    st.className = "notice" + (kind ? " " + kind : "");
  }

  /* ---------- "Here's what we read from your paste" ---------- */
  var STATUS = {
    look: ['<span class="badge recognition-attention">Needs a look</span>', "More than one player fits. Check the spelling, or leave this line out."],
    missing: ['<span class="badge recognition-attention">Not found</span>', "No player found. Edit or leave this line out."],
    kdef: ['<span class="badge">Not evaluated</span>', "Kickers and defenses are not evaluated for trades."]
  };
  function teamRows(t) {
    var out = t.players.map(function (p) {
      var what = esc(p.name) + (p.pos ? " · " + esc(p.pos) : "") + (p.team ? " · " + esc(p.team) : "");
      return "<tr><td>" + esc(p.line || p.name) + '</td><td><span class="badge recognition-ok">Matched</span></td><td>' + what + "</td></tr>";
    });
    t.unmatched.forEach(function (u) {
      var s = STATUS[u.reason] || STATUS.missing;
      out.push("<tr><td>" + esc(u.line) + "</td><td>" + s[0] + "</td><td>" + s[1] + "</td></tr>");
    });
    return out.join("") || '<tr><td colspan="3">No players read for this team yet.</td></tr>';
  }
  function summaryText(res) {
    var head = "Found " + plural(res.teams.length, "team") + " and " + plural(res.matched, "player") + ".";
    var issues = [];
    if (res.look) issues.push(res.look + " need" + (res.look === 1 ? "s" : "") + " a look");
    if (res.missing) issues.push(res.missing + " not found");
    if (res.notEvaluated) issues.push(res.notEvaluated + " kicker or defense line" + (res.notEvaluated === 1 ? "" : "s") + " not evaluated");
    return head + (issues.length ? " " + issues.join(", ").replace(/^./, function (c) { return c.toUpperCase(); }) + "." : "");
  }
  function showResult(res) {
    var card = $("recognized");
    $("recognition-summary").textContent = summaryText(res);
    $("recognition-teams").innerHTML = res.teams.map(function (t, i) {
      var issues = t.unmatched.filter(function (u) { return u.reason !== "kdef"; }).length;
      var label = esc(t.name) + " · " + plural(t.players.length, "player") + " matched" + (issues ? " · " + issues + " to check" : "");
      return '<details class="recognition-team"' + (issues || res.teams.length <= 2 ? " open" : "") + "><summary>" + label + "</summary>"
        + '<div class="table-wrap"><table><caption class="sr-only">Pasted lines for ' + esc(t.name) + " and what we matched</caption>"
        + '<thead><tr><th scope="col">Pasted line</th><th scope="col">Status</th><th scope="col">What we matched</th></tr></thead><tbody>'
        + teamRows(t) + "</tbody></table></div></details>";
    }).join("");
    var partial = $("recognition-partial");
    if (partial) partial.hidden = !(res.look || res.missing);
    card.hidden = false;
    $("recognize-button").setAttribute("aria-expanded", "true");
  }
  function hideResult() {
    var card = $("recognized");
    if (card) card.hidden = true;
    var b = $("recognize-button"); if (b) b.setAttribute("aria-expanded", "false");
  }

  /* ---------- edit-names box ---------- */
  function showEditNames(names, why) {
    var box = $("edit-names");
    $("edit-names-why").textContent = why;
    $("edit-names-input").value = (names || []).join("\n");
    $("edit-names-input").placeholder = "One team name per line";
    box.hidden = false;
  }
  function hideEditNames() { var box = $("edit-names"); if (box) box.hidden = true; }

  /* ---------- reading ---------- */
  var busy = false;
  function check(focus, scroll) {
    var text = $("rosters").value;
    var oneTeam = $("one-team-error");
    oneTeam.hidden = true;
    $("rosters").removeAttribute("aria-invalid");
    if (!text.trim()) { hideResult(); hideEditNames(); status("Paste every team's roster first.", "warn"); return Promise.resolve(null); }
    if (busy) return Promise.resolve(null);
    busy = true;
    status("Reading your rosters...", "");
    return whenRows().then(function (r) {
      busy = false;
      var res = DDF.leaguePaste.read(text, r, {table: table()});
      if (res.ok) {
        hideEditNames();
        showResult(res);
        save(DDF.leaguePaste.record(res, "paste"));
        status("Check the list below, then confirm your team.", "ok");
        if (scroll) $("recognized").scrollIntoView({block: "start"});
        if (focus) $("recognition-title").focus({preventScroll: true});
        return res;
      }
      hideResult();
      drop();
      if (res.reason === "one-team") {
        oneTeam.hidden = false;
        $("rosters").setAttribute("aria-invalid", "true");
        status("That looks like one team's page. We need every team's roster.", "warn");
        oneTeam.scrollIntoView({block: "center"});
        return res;
      }
      status("We could not find any teams in that paste. Make sure you copied the page that lists every team's roster, then try again, or add your rosters manually.", "warn");
      showEditNames(res.names, res.names.length
        ? "We found " + plural(res.names.length, "possible team name") + ", but could not split the players by team. Fix the names so each one matches a team name in your paste, one per line."
        : "We could not find team names in your paste. If you copied the right page, type each team name as it appears there, one per line.");
      return res;
    }).catch(function () {
      busy = false;
      status("Player values are still loading. Try again in a moment.", "warn");
      return null;
    });
  }
  function readAgain() {
    var names = $("edit-names-input").value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (names.length < 2) { $("edit-names-status").textContent = "Add at least two team names, one per line."; return; }
    whenRows().then(function (r) {
      var res = DDF.leaguePaste.readWithNames($("rosters").value, names, r, {table: table()});
      if (!res.ok) { $("edit-names-status").textContent = "We still could not read this paste. Enter your rosters manually instead."; return; }
      $("edit-names-status").textContent = "";
      hideEditNames();
      showResult(res);
      save(DDF.leaguePaste.record(res, "paste"));
      status("Check the list below, then confirm your team.", "ok");
      $("recognized").scrollIntoView({block: "start"});
      $("recognition-title").focus({preventScroll: true});
    }).catch(function () { $("edit-names-status").textContent = "Player values are still loading. Try again in a moment."; });
  }
  function editNamesFromCard() {
    var p = kept();
    showEditNames(p ? p.teams.map(function (t) { return t.name; }) : [], "Fix any team name so it matches your paste, one per line, then read your rosters again.");
    $("edit-names-input").focus();
  }

  /* ---------- manual entry ---------- */
  var manual = {teams: []};
  function manualRecord() {
    return {v: 1, source: "manual", site: "unknown", me: null,
      teams: manual.teams.map(function (t) { return {name: t.name, players: t.players.slice(), unmatched: []}; })};
  }
  function manualSave() { if (manual.teams.length) save(manualRecord()); else drop(); }
  function manualNames() {
    var names = $("manual-names").value.split(/\r?\n/).map(function (s) { return s.replace(/\s+/g, " ").trim().slice(0, 40); }).filter(Boolean);
    var byName = {};
    manual.teams.forEach(function (t) { byName[t.name.toLowerCase()] = t; });
    manual.teams = names.slice(0, 20).map(function (n) { return byName[n.toLowerCase()] || {name: n, players: []}; });
    var sel = $("manual-team"), was = sel.value;
    sel.innerHTML = manual.teams.map(function (t, i) { return '<option value="' + i + '">' + esc(t.name) + "</option>"; }).join("");
    if (was && manual.teams[Number(was)]) sel.value = was;
    manualRender();
    manualSave();
  }
  function manualRender() {
    var t = manual.teams[Number($("manual-team").value)] || null;
    $("manual-roster-title").textContent = t ? t.name + " · " + plural(t.players.length, "player") : "Add your team names first";
    $("manual-rows").innerHTML = t && t.players.length ? t.players.map(function (p, i) {
      return "<tr><td>" + esc(p.name) + "</td><td>" + esc(p.pos) + '</td><td><button type="button" class="link-button" data-remove="' + i + '">Remove<span class="sr-only"> ' + esc(p.name) + "</span></button></td></tr>";
    }).join("") : '<tr><td colspan="3">' + (t ? "No players yet. Find a player above and add them." : "Type each team's name above, one per line.") + "</td></tr>";
  }
  function fillPlayerOptions() {
    var r = rows();
    if (!r) return;
    $("player-options").innerHTML = r.map(function (p) { return '<option value="' + esc(p.name + " (" + p.pos + (p.team ? ", " + p.team : "") + ")") + '"></option>'; }).join("");
  }
  function manualAdd() {
    var st = $("manual-status"), t = manual.teams[Number($("manual-team").value)];
    if (!t) { st.textContent = "Add your team names first."; return; }
    var q = $("find-player").value.trim(), r = rows();
    if (!r) { st.textContent = "Player values are still loading. Try again in a moment."; return; }
    var name = q.replace(/\s*\([^)]*\)\s*$/, "").toLowerCase();
    var hits = r.filter(function (p) { return p.name.toLowerCase() === name; });
    if (hits.length > 1) { var exact = hits.filter(function (p) { return (p.name + " (" + p.pos + (p.team ? ", " + p.team : "") + ")") === q; }); if (exact.length) hits = exact; }
    if (hits.length !== 1) { st.textContent = hits.length ? "More than one player has that name. Check the list and add the right player." : "No player found with that name. Check the spelling."; return; }
    var p = hits[0], key = String(p.player_key);
    var owner = manual.teams.filter(function (x) { return x.players.some(function (y) { return y.key === key; }); })[0];
    if (owner) { st.textContent = p.name + " is already on " + owner.name + "."; return; }
    var ids = {}; table().forEach(function (row, i) { var k = String(row).split("|")[3]; if (k && ids[k] === undefined) ids[k] = i; });
    t.players.push({name: p.name, key: key, pos: p.pos, team: p.team, slot: "", line: p.name, id: ids[key] === undefined ? null : ids[key]});
    $("find-player").value = "";
    st.textContent = "Added " + p.name + " to " + t.name + ".";
    manualRender();
    manualSave();
  }

  /* ---------- wiring ---------- */
  function init() {
    var form = $("roster-form");
    if (!form || !DDF.leaguePaste) return;
    form.addEventListener("submit", function (e) { e.preventDefault(); check(true, true); });
    var ta = $("rosters");
    ta.addEventListener("paste", function () { setTimeout(function () { check(false, true); }, 0); });
    ta.addEventListener("input", function () {
      var p = kept();
      if (p && p.source === "paste") drop();
      hideResult();
      if (!ta.value.trim()) { status("", ""); hideEditNames(); }
    });
    $("edit-names-go").addEventListener("click", readAgain);
    $("edit-team-names").addEventListener("click", editNamesFromCard);
    $("manual-names").addEventListener("input", manualNames);
    $("manual-team").addEventListener("change", manualRender);
    $("manual-add").addEventListener("click", manualAdd);
    $("find-player").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); manualAdd(); } });
    $("manual-rows").addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-remove]"), t = manual.teams[Number($("manual-team").value)];
      if (!b || !t) return;
      t.players.splice(Number(b.getAttribute("data-remove")), 1);
      manualRender();
      manualSave();
    });
    /* coming back to this page in the same tab: show what was kept */
    var p = kept();
    if (p && p.source === "manual") {
      manual.teams = p.teams.map(function (t) { return {name: t.name, players: (t.players || []).slice()}; });
      $("manual-names").value = manual.teams.map(function (t) { return t.name; }).join("\n");
      manualNames();
    } else manualRender();
    if (DDF.engine && DDF.engine.ready) DDF.engine.ready.then(fillPlayerOptions).catch(function () {});
    if (p && p.source === "paste" && ta.value.trim()) check(false);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  DDF.connectEntry = {check: check, detectDevice: detectDevice};
})();
