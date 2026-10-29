// Trade Value v2 — Trade target answer card (JEG-1274, part of JEG-1139). Isolated component, not wired to a route.
//
// Renders one player's existing, precomputed target answer: stable identity, the Buy / Sell / Fair price call, its
// reasons, the supplied values and which sources priced the player. It computes nothing: no gaps, ranks, medians,
// thresholds or defaults. Every number is shown exactly as supplied (a `display` string verbatim, else the number
// itself), a real 0 stays "0", and a missing value says "No value" with its reason, never 0. The input is never
// mutated, and the card reads no storage and makes no network request. The evidence detail is an injected slot:
// the reusable evidence internals belong to the Compare evidence view (JEG-1271), so this card only mounts whatever
// `renderDetail` draws. Contract: docs/design/target-answer-card-contract.md.
(function (root) {
  "use strict";

  const STATES = ["buy", "sell", "fair", "empty", "missing", "unavailable"];
  const SIDES = ["buy", "sell", "fair"];
  const SOURCE_STATUSES = ["priced", "waiver", "missing", "unavailable"];
  // Placeholder words until the approved copy (JEG-1130 / JEG-1212) lands; a caller passes `labels` to replace them.
  const LABELS = Object.freeze({
    buy: "Buy", sell: "Sell", fair: "Fair price",
    noValue: "No value", sources: "Sources", detail: "Evidence details",
    empty: "No target to show for this selection.", missing: "No answer for this player yet.",
    unavailable: "Target answers are unavailable right now.", detailFailed: "Details could not be shown.",
    priced: "Priced", waiver: "At waiver line", sourceMissing: "Not priced", sourceUnavailable: "Unavailable",
  });

  const finite = v => typeof v === "number" && Number.isFinite(v);
  const str = v => (typeof v === "string" && v.trim() ? v : null);
  const esc = v => String(v).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  // The one way a number becomes text: the supplied display string, else the number as given. -0 shows as "0".
  function valueText(item) {
    if (str(item.display)) return item.display;
    if (finite(item.value)) return Object.is(item.value, -0) ? "0" : String(item.value);
    return null;
  }

  function identity(player) {
    if (!player || typeof player !== "object" || !str(player.id) || !str(player.name)) return null;
    return {id: player.id, name: player.name, pos: str(player.pos), team: str(player.team)};
  }

  function values(list, labels, problems) {
    return (Array.isArray(list) ? list : []).map((item, i) => {
      const key = str(item && item.key) || `value-${i + 1}`;
      const text = item ? valueText(item) : null;
      if (item && item.value !== null && item.value !== undefined && !finite(item.value)) problems.push(`value ${key} is not a number`);
      return {key, label: str(item && item.label) || key, text: text === null ? labels.noValue : text,
        raw: item && finite(item.value) ? item.value : null, isMissing: text === null, reason: text === null ? str(item && item.reason) : null};
    });
  }

  function sources(list, labels, problems) {
    const words = {priced: labels.priced, waiver: labels.waiver, missing: labels.sourceMissing, unavailable: labels.sourceUnavailable};
    return (Array.isArray(list) ? list : []).map((item, i) => {
      const key = str(item && item.key) || `source-${i + 1}`;
      let status = item && item.status;
      if (!SOURCE_STATUSES.includes(status)) { problems.push(`source ${key} has an unknown status`); status = "missing"; }
      const shown = status === "priced" || status === "waiver";
      const text = shown ? valueText(item) : null;
      return {key, name: str(item && item.name) || key, status, statusWord: words[status],
        text: shown ? (text === null ? labels.noValue : text) : null, reason: str(item && item.reason)};
    });
  }

  // input: the precomputed answer (see the contract doc). labels: optional word overrides.
  function viewModel(input, labels) {
    const L = Object.assign({}, LABELS, labels || {});
    const problems = [];
    const c = input && typeof input === "object" ? input : null;
    const fixture = c && c.fixture && str(c.fixture.label) ? {kind: str(c.fixture.kind), label: c.fixture.label} : null;
    const base = {state: "empty", player: null, sideWord: null, reasons: [], values: [], sources: [], message: null,
      missing: [], hasDetail: false, detail: null, fixture, problems};
    if (!c || c.status === "empty") return Object.assign(base, {message: (c && str(c.message)) || L.empty});
    if (c.status === "unavailable") return Object.assign(base, {state: "unavailable", message: str(c.reason) || L.unavailable});
    if (c.status !== undefined && c.status !== "ready") problems.push("unknown status");
    const player = identity(c.player);
    if (!player) problems.push("no stable player identity");
    const vm = Object.assign(base, {player, values: values(c.values, L, problems), sources: sources(c.sources, L, problems),
      hasDetail: c.detail !== null && c.detail !== undefined, detail: c.detail === undefined ? null : c.detail});
    const side = c.answer && typeof c.answer === "object" ? c.answer.side : null;
    if (c.answer && !SIDES.includes(side)) problems.push("unknown answer");
    if (!player || problems.includes("unknown status") || !SIDES.includes(side)) {
      vm.state = "missing";
      vm.message = str(c.message) || L.missing;
      vm.missing = (Array.isArray(c.missing) ? c.missing : []).map(str).filter(Boolean);
      return vm;
    }
    vm.state = side;
    vm.sideWord = L[side];
    vm.reasons = (Array.isArray(c.answer.reasons) ? c.answer.reasons : []).map(str).filter(Boolean);
    return vm;
  }

  const panelId = (uid, key) => `${uid}-${key}`;

  function disclosure(uid, key, word, open, body) {
    return `<div class="tac-disclosure" data-key="${key}">` +
      `<button type="button" class="tac-toggle" data-tac-toggle="${key}" data-tac-focus="${key}" aria-expanded="${open}" aria-controls="${panelId(uid, key)}">${esc(word)}</button>` +
      `<div class="tac-panel" id="${panelId(uid, key)}"${open ? "" : " hidden"}>${body}</div></div>`;
  }

  // Pure: view model to HTML. opts: {uid, open: {sources, detail}, headingLevel, labels}.
  function markup(vm, opts) {
    const o = opts || {};
    const uid = o.uid || "tac";
    const open = o.open || {};
    const L = Object.assign({}, LABELS, o.labels || {});
    const h = [2, 3, 4, 5, 6].includes(o.headingLevel) ? o.headingLevel : 3;
    const out = [];
    const pid = vm.player ? ` data-player-id="${esc(vm.player.id)}"` : "";
    out.push(`<article class="tac tac--${vm.state}" data-state="${vm.state}"${pid}${vm.player ? ` aria-labelledby="${uid}-name"` : ""}>`);
    if (vm.fixture) out.push(`<p class="tac-fixture">${esc(vm.fixture.label)}</p>`);
    if (vm.player) {
      const meta = [vm.player.pos, vm.player.team].filter(Boolean).map(esc).join(" · ");
      out.push(`<header class="tac-head"><h${h} class="tac-name" id="${uid}-name">${esc(vm.player.name)}</h${h}>` +
        (meta ? `<p class="tac-meta">${meta}</p>` : "") + "</header>");
    }
    if (vm.sideWord) out.push(`<p class="tac-answer"><span class="tac-side tac-side--${vm.state}">${esc(vm.sideWord)}</span></p>`);
    if (vm.message) out.push(`<p class="tac-message">${esc(vm.message)}</p>`);
    if (vm.missing.length) out.push(`<ul class="tac-missing">${vm.missing.map(m => `<li>${esc(m)}</li>`).join("")}</ul>`);
    if (vm.reasons.length) out.push(`<ul class="tac-reasons">${vm.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>`);
    if (vm.values.length) {
      out.push(`<dl class="tac-values">${vm.values.map(v =>
        `<div class="tac-value${v.isMissing ? " is-missing" : ""}" data-key="${esc(v.key)}"><dt>${esc(v.label)}</dt>` +
        `<dd${v.raw === null ? "" : ` data-value="${esc(v.raw)}"`}>${esc(v.text)}</dd>` +
        (v.reason ? `<dd class="tac-reason">${esc(v.reason)}</dd>` : "") + "</div>").join("")}</dl>`);
    }
    if (vm.sources.length) {
      const body = `<ul class="tac-sources">${vm.sources.map(s =>
        `<li class="tac-source is-${s.status}" data-key="${esc(s.key)}"><span class="tac-source-name">${esc(s.name)}</span>` +
        `<span class="tac-source-status">${esc(s.statusWord)}</span>` +
        (s.text !== null ? `<span class="tac-source-value">${esc(s.text)}</span>` : "") +
        (s.reason ? `<span class="tac-reason">${esc(s.reason)}</span>` : "") + "</li>").join("")}</ul>`;
      out.push(disclosure(uid, "sources", L.sources, Boolean(open.sources), body));
    }
    if (vm.hasDetail) out.push(disclosure(uid, "detail", L.detail, Boolean(open.detail), '<div class="tac-detail-slot"></div>'));
    out.push("</article>");
    return out.join("");
  }

  let mounts = 0;

  // Mounts the card into `el`. opts.renderDetail(slot, detail, {playerId, state}) draws the evidence detail when its
  // disclosure opens and may return a cleanup function. Open/closed state lives in this handle only (never storage)
  // and resets when the player changes; focus on a toggle survives a re-render.
  function mount(el, opts) {
    const o = opts || {};
    const uid = `tac${++mounts}`;
    let input = null;
    let vm = null;
    let playerId = null;
    let cleanup = null;
    const open = {sources: false, detail: false};

    function unmountDetail() {
      const fn = cleanup;
      cleanup = null;
      if (typeof fn === "function") { try { fn(); } catch (e) { /* a failing cleanup never breaks the card */ } }
    }
    function mountDetail() {
      const slot = el.querySelector(".tac-detail-slot");
      if (!slot || !vm || !vm.hasDetail) return;
      if (typeof o.renderDetail !== "function") return;
      try {
        const fn = o.renderDetail(slot, vm.detail, {playerId: vm.player ? vm.player.id : null, state: vm.state});
        cleanup = typeof fn === "function" ? fn : null;
      } catch (e) {
        slot.textContent = Object.assign({}, LABELS, o.labels || {}).detailFailed;
      }
    }
    function render() {
      const active = el.ownerDocument && el.ownerDocument.activeElement;
      const focusKey = active && el.contains(active) && active.getAttribute ? active.getAttribute("data-tac-focus") : null;
      unmountDetail();
      vm = viewModel(input, o.labels);
      const id = vm.player ? vm.player.id : null;
      if (id !== playerId) { open.sources = false; open.detail = false; playerId = id; }
      if (!vm.sources.length) open.sources = false;
      if (!vm.hasDetail) open.detail = false;
      el.innerHTML = markup(vm, {uid, open, headingLevel: o.headingLevel, labels: o.labels});
      el.setAttribute("data-state", vm.state);
      if (open.detail) mountDetail();
      if (focusKey) {
        const again = el.querySelector(`[data-tac-focus="${focusKey}"]`);
        if (again) again.focus();
      }
    }
    function setOpen(key, want) {
      if (key !== "sources" && key !== "detail") return;
      const button = el.querySelector(`[data-tac-toggle="${key}"]`);
      if (!button) return;
      const panel = el.querySelector(`#${panelId(uid, key)}`);
      if (open[key] === want) return;
      open[key] = want;
      button.setAttribute("aria-expanded", String(want));
      if (panel) panel.hidden = !want;
      if (key === "detail") { if (want) mountDetail(); else unmountDetail(); }
    }
    function onClick(event) {
      const button = event.target.closest && event.target.closest("[data-tac-toggle]");
      if (!button || !el.contains(button)) return;
      const key = button.getAttribute("data-tac-toggle");
      setOpen(key, !open[key]);
    }
    function onKeydown(event) {
      if (event.key !== "Escape") return;
      const panel = event.target.closest && event.target.closest(".tac-panel");
      if (!panel || panel.hidden) return;
      const key = panel.parentElement.getAttribute("data-key");
      setOpen(key, false);
      const button = el.querySelector(`[data-tac-toggle="${key}"]`);
      if (button) button.focus();
    }
    el.addEventListener("click", onClick);
    el.addEventListener("keydown", onKeydown);
    return {
      update(next) { input = next; render(); },
      open(key) { setOpen(key, true); },
      close(key) { setOpen(key, false); },
      isOpen(key) { return Boolean(open[key]); },
      viewModel() { return vm; },
      destroy() {
        unmountDetail();
        el.removeEventListener("click", onClick);
        el.removeEventListener("keydown", onKeydown);
        el.innerHTML = "";
        el.removeAttribute("data-state");
      },
    };
  }

  const api = {STATES, SIDES, SOURCE_STATUSES, LABELS, valueText, viewModel, markup, mount};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTargetAnswerCard = api;
})(typeof window !== "undefined" ? window : globalThis);
