// Trade Value v2 — the inputs status strip.
//
// Soft notes under the league row that say what the numbers below were computed from, so a reader does not take
// results made for default settings, a shared link's settings or a stale or missing roster as their own. They inform;
// they never block a tab. Reads: TradeValueV2.leagueInputs() (where the league settings came from) and the workspace
// store (rosters). Each note can be dismissed for the visit (sessionStorage); a note that is still true on the next
// visit shows again. Redraws on "ddf:inputs-changed", "ddf:league-settings-changed", hashchange and any store change.
(function (root) {
  "use strict";

  const DISMISS_KEY = "ddf.v2.inputs-dismissed";
  const STALE_DAYS = 7;
  // The tabs whose results are for the reader's own roster.
  const ROSTER_TABS = ["#find-trade", "#find-league", "#waivers"];
  const DAY_MS = 86400000;

  const $ = id => document.getElementById(id);
  let dismissed = {};
  try { dismissed = JSON.parse(root.sessionStorage.getItem(DISMISS_KEY) || "{}") || {}; } catch (error) { dismissed = {}; }
  const dismiss = id => {
    dismissed[id] = true;
    try { root.sessionStorage.setItem(DISMISS_KEY, JSON.stringify(dismissed)); } catch (error) { /* held in memory for the visit */ }
    render();
  };

  function el(tag, attrs, kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    });
    (kids || []).forEach(kid => node.appendChild(kid));
    return node;
  }

  function host() {
    let box = $("v2InputsStatus");
    if (box) return box;
    const league = $("v2Context") || $("v2League");   // JEG-1119: the context row replaced the league bar
    if (!league || !league.parentNode) return null;
    box = el("div", {id: "v2InputsStatus", class: "v2-inputs", "aria-label": "Status of your inputs", role: "region", hidden: ""});
    league.parentNode.insertBefore(box, league.nextSibling);
    return box;
  }

  const hashBase = () => String(root.location.hash || "").split("?")[0];
  const onRosterTab = () => ROSTER_TABS.includes(hashBase());
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // Pure: the notes for this state. {id, level: "info" | "warn", text, action?: {label, run}}.
  function notesFor(input) {
    const out = [];
    const league = input.league;
    if (league) {
      const label = league.label ? ` (${league.label})` : "";
      if (league.source === "link") {
        out.push({id: "league-link", level: "warn", edit: true,
          text: `These numbers use the league settings from a shared link${label}. They last for this visit only and are not saved to your browser.`});
      } else if (league.source === "default") {
        out.push({id: "league-default", level: "info", edit: true,
          text: `These numbers use the site's default league settings${label}. If your league is different, set it so the values fit your league.`});
      }
      (league.notes || []).forEach((text, i) => out.push({id: `league-note-${i}`, level: "warn", text}));
      if (league.storage === "full") out.push({id: "storage-full", level: "warn", text: "Browser storage is full, so your league settings were not saved. They will reset when you reload."});
      else if (league.storage === "unavailable") out.push({id: "storage-off", level: "warn", text: "This browser is blocking storage, so your league settings and rosters will not be remembered after you close the tab."});
    }
    const ws = input.workspace;
    if (ws) {
      const blocked = ws.status === "unavailable" || ws.loadStatus === "unavailable";
      if (blocked && !out.some(n => n.id === "storage-off")) out.push({id: "storage-off", level: "warn", text: "This browser is blocking storage, so your league settings and rosters will not be remembered after you close the tab."});
      if (ws.status === "full") out.push({id: "roster-full", level: "warn", text: "Browser storage is full, so your latest roster changes were not saved."});
      if (ws.loadStatus === "corrupt" || ws.loadStatus === "version") {
        out.push({id: "roster-unreadable", level: "warn", text: "Your saved rosters could not be read, so none are loaded. Entering a roster replaces them."});
      }
      if (input.rosterTab) {
        if (!ws.teamCount) {
          out.push({id: "roster-none", level: "warn", text: "No roster entered yet, so nothing here is for your team. Enter your roster to see results for it.", link: {label: "Enter your roster", href: "v2/#find-trade"}});
        } else if (!ws.myTeam) {
          out.push({id: "roster-no-mine", level: "warn", text: `${plural(ws.teamCount, "team")} saved, but none is marked as yours, so results are not for your team.`, link: {label: "Mark your team", href: "v2/#find-trade"}});
        } else if (ws.myUpdatedAt && input.now - ws.myUpdatedAt > STALE_DAYS * DAY_MS) {
          const days = Math.floor((input.now - ws.myUpdatedAt) / DAY_MS);
          out.push({id: "roster-stale", level: "info", text: `Your roster was last updated ${days} days ago. If you have made moves since, update it so results match.`, link: {label: "Update roster", href: "v2/#find-trade"}});
        } else {
          out.push({id: "roster-ok", level: "info", quiet: true, text: `Your roster${ws.myName ? ` (${ws.myName})` : ""} and ${plural(Math.max(0, ws.teamCount - 1), "other team")} are saved in this browser.`});
        }
      }
    }
    return out;
  }

  function snapshot() {
    const V = root.TradeValueV2;
    const W = root.TradeValueWorkspace;
    const input = {now: Date.now(), rosterTab: onRosterTab(), league: null, workspace: null};
    try { input.league = V && V.leagueInputs ? V.leagueInputs() : null; } catch (error) { input.league = null; }
    try {
      const store = W && W.store;
      if (store) {
        const w = store.get();
        const mine = w.teams.find(t => t.id === w.myTeamId) || null;
        input.workspace = {status: store.status(), loadStatus: store.loadStatus(), teamCount: w.teams.length, myTeam: Boolean(mine),
          myName: mine ? mine.name : "", myUpdatedAt: mine && mine.entries.length ? mine.updatedAt : 0};
      }
    } catch (error) { input.workspace = null; }
    return input;
  }

  function render() {
    const box = host();
    if (!box) return;
    const shown = notesFor(snapshot()).filter(n => !dismissed[n.id]);
    box.replaceChildren(...shown.map(n => el("div", {class: `v2-inputs-note is-${n.level}${n.quiet ? " is-quiet" : ""}`, "data-note": n.id}, [
      el("div", {class: "v2-wrap v2-inputs-in"}, [
        el("span", {class: "v2-inputs-text", title: n.text, text: n.text}),
        ...(n.edit ? [el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Edit league",
          onclick: () => { const b = $("v2EditLeague"); if (b) b.click(); }})] : []),
        ...(n.link ? [el("a", {class: "v2-link", href: n.link.href, text: n.link.label})] : []),
        el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Dismiss", "aria-label": `Dismiss: ${n.text}`, onclick: () => dismiss(n.id)})])])));
    box.hidden = !shown.length;
  }

  const api = {notesFor, render, STALE_DAYS};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueInputsStatus = api;

  document.addEventListener("ddf:inputs-changed", render);
  document.addEventListener("ddf:league-settings-changed", render);
  root.addEventListener("hashchange", render);
  const attach = () => {
    render();
    const store = root.TradeValueWorkspace && root.TradeValueWorkspace.store;
    if (store) { store.onChange(render); store.onStatus(render); }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attach);
  else attach();
})(typeof window !== "undefined" ? window : globalThis);
