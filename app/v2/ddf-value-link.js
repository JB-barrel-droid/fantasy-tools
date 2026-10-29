// JEG-1225 (slice 4a of the JEG-1224 plan): the value context a share link carries, read and written in one place.
// A link says which basis DDF Value follows and which player overrides apply:
//   basis=fantasycalc | basis=blend:espn.60_razzball.40          (absent = our methodology)
//   ov=2227:58.0,1110:+5                                         (a few players; a sign marks an adjustment)
//   ov=z:<base64url> | ov=z2:<base64url>                         (packed, past PACK_AFTER overrides)
//   valuecontext=1                                               (the link carries the sender's whole context)
// The site's Overrides tab (overrides.js), get-values and the MCP function all use this module, so there is one
// reader of the link format. Pure: no DOM, no storage. Plain script; also loads under node/Deno (UMD), and
// get-values loads the published copy the way it loads value-model.js.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DDFValueLink = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // The seven pipeline sources a basis may name (curve-widget.js BASIS_SOURCE_KEYS).
  const BASIS_KEYS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];
  const PACK_AFTER = 6;       // more overrides than this are packed in the link
  // JEG-1058: the fixed-pie scale an override lives on (spec 3.6).
  const OVERRIDE_MIN = 0;
  const OVERRIDE_MAX = 100;

  const finite = v => typeof v === "number" && Number.isFinite(v);
  const round1 = v => Math.round(v * 10) / 10;
  const clampWeight = v => Math.min(100, Math.max(1, Math.round(Number(v) || 1)));
  const isAdjustment = entry => !!(entry && typeof entry === "object" && entry.type === "adjustment");
  // Every override that arrives from outside the editor (a share link, an import, a saved record) is put on the
  // scale the editor shows: an absolute value between 0 and 100, an adjustment within the scale's span. The value it
  // produces is the same either way, because the result is capped anyway; the adjustment is capped so it always
  // fits a packed link.
  const clampOverrideValue = v => round1(Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, v)));
  const clampOverrideDelta = d => round1(Math.min(OVERRIDE_MAX, Math.max(-OVERRIDE_MAX, d)));
  // An override as the link and the editor hold it: a number (absolute) or {type: "adjustment", delta}. null when
  // it cannot be used (not a number, an absolute below zero, an adjustment of zero).
  function normalizeEntry(entry) {
    if (isAdjustment(entry)) {
      const delta = Number(entry.delta);
      if (!Number.isFinite(delta) || delta === 0) return null;
      return {type: "adjustment", delta: clampOverrideDelta(delta)};
    }
    if (!finite(entry) || entry < OVERRIDE_MIN) return null;
    return clampOverrideValue(entry);
  }

  // ---------- packed overrides ----------
  // ov=z: is 3 bytes of player key + 2 bytes of tenths per override (absolute values only, the original layout).
  // ov=z2: adds a type byte (0 absolute, 1 adjustment) and signs the tenths, so a delta can be negative.
  const b64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64 = text => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), ch => ch.charCodeAt(0));
  function packOverrides(map) {
    const bytes = [];
    Object.keys(map).forEach(key => {
      const k = Number(key);
      const tenths = Math.round(map[key] * 10);
      if (!Number.isInteger(k) || k < 0 || k > 0xFFFFFF || tenths < 0 || tenths > 0xFFFF) return;
      bytes.push((k >> 16) & 255, (k >> 8) & 255, k & 255, (tenths >> 8) & 255, tenths & 255);
    });
    return b64(bytes);
  }
  function unpackOverrides(text) {
    const bytes = unb64(text);
    const out = {};
    for (let i = 0; i + 4 < bytes.length; i += 5) {
      const entry = normalizeEntry(((bytes[i + 3] << 8) | bytes[i + 4]) / 10);
      if (entry !== null) out[String((bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2])] = entry;
    }
    return out;
  }
  function packOverridesWithTypes(map) {
    const bytes = [];
    Object.keys(map).forEach(key => {
      const k = Number(key);
      const entry = map[key];
      const adjustment = isAdjustment(entry);
      const tenths = Math.round((adjustment ? Number(entry.delta) : Number(entry)) * 10);
      if (!Number.isInteger(k) || k < 0 || k > 0xFFFFFF) return;
      if (!Number.isFinite(tenths)) return;
      // The tenths are inside the two bytes they travel in: an override is on the scale, so this is the same
      // number, never a dropped player.
      const packed = Math.min(32767, Math.max(-32768, tenths));
      bytes.push((k >> 16) & 255, (k >> 8) & 255, k & 255, adjustment ? 1 : 0, (packed >> 8) & 255, packed & 255);
    });
    return b64(bytes);
  }
  function unpackOverridesWithTypes(text) {
    const bytes = unb64(text);
    const out = {};
    for (let i = 0; i + 5 < bytes.length; i += 6) {
      const key = String((bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]);
      const raw = (bytes[i + 4] << 8) | bytes[i + 5];
      const tenths = raw >= 32768 ? raw - 65536 : raw;
      const value = tenths / 10;
      const entry = bytes[i + 3] === 1 ? normalizeEntry({type: "adjustment", delta: value}) : normalizeEntry(value);
      if (entry !== null) out[key] = entry;
    }
    return out;
  }

  // ---------- writing ----------
  // A basis record ({mode: "single", source} or {mode: "blend", sources, weights}; getBasis() has the same fields)
  // -> the basis= text, or null for our methodology.
  function formatBasisParam(rec) {
    if (!rec || typeof rec !== "object" || !rec.mode || rec.mode === "default") return null;
    if (rec.mode === "single") return rec.source ? String(rec.source) : null;
    if (rec.mode !== "blend") return null;
    const sources = Array.isArray(rec.sources) ? rec.sources : Object.keys(rec.weights || {});
    return sources.length ? `blend:${sources.map(key => `${key}.${rec.weights[key]}`).join("_")}` : null;
  }
  // One override in a link: key:value for an absolute value, key:+5 for an adjustment.
  const ovPart = (key, entry) => (isAdjustment(entry)
    ? `${key}:${Number(entry.delta) >= 0 ? "+" : ""}${round1(Number(entry.delta))}`
    : `${key}:${entry}`);
  // {player_key: override} -> the ov= text, or null when there are none.
  function formatOvParam(map) {
    const keys = Object.keys(map || {});
    if (!keys.length) return null;
    if (keys.some(key => isAdjustment(map[key]))) {
      return keys.length > PACK_AFTER ? `z2:${packOverridesWithTypes(map)}` : keys.map(key => ovPart(key, map[key])).join(",");
    }
    return keys.length > PACK_AFTER ? `z:${packOverrides(map)}` : keys.map(key => `${key}:${map[key]}`).join(",");
  }

  // ---------- reading ----------
  // basis= text -> {mode: "single", source} | {mode: "blend", sources, weights}, or null when absent or unreadable.
  // Unknown sources and weights below 1 are left out; weights are whole percents 1-100.
  function parseBasisParam(text) {
    if (!text) return null;
    if (text.startsWith("blend:")) {
      const sources = [];
      const weights = {};
      text.slice(6).split("_").forEach(part => {
        const [key, w] = part.split(".");
        if (BASIS_KEYS.includes(key) && Number(w) >= 1) { sources.push(key); weights[key] = clampWeight(w); }
      });
      return sources.length ? {mode: "blend", sources, weights} : null;
    }
    return BASIS_KEYS.includes(text) ? {mode: "single", source: text} : null;
  }
  // ov= text -> {player_key: override}, or null when absent or nothing in it is usable.
  // JEG-1058: a value that starts with + or - is an adjustment (ov=2227:+5); a plain number is an absolute value.
  function parseOvParam(text) {
    if (!text) return null;
    let map = {};
    try {
      if (text.startsWith("z2:")) map = unpackOverridesWithTypes(text.slice(3));
      else if (text.startsWith("z:")) map = unpackOverrides(text.slice(2));
      else text.split(",").forEach(part => {
        const [key, v] = part.split(":");
        if (!/^\d+$/.test(key) || v === undefined || v === "") return;
        // A sign means an adjustment. A leading space is the "+" that a URL parser turned into a space
        // (URLSearchParams reads "+" as a space), so it is a sign too.
        if (/^[+-]/.test(v) || /^\s/.test(v)) {
          const entry = normalizeEntry({type: "adjustment", delta: Number(v)});
          if (entry !== null) map[key] = entry;
        } else {
          const entry = normalizeEntry(Number(v));
          if (entry !== null) map[key] = entry;
        }
      });
    } catch (error) { return null; }
    return Object.keys(map).length ? map : null;
  }
  // A link's value context. `params` is URLSearchParams (or anything with get()) or a plain object
  // {basis, ov, valuecontext}. Returns {present, complete, basisText, ovText, basis, overrides, unread}:
  //   present   the link says anything about values (a basis, overrides, or the complete marker)
  //   complete  valuecontext=1: the sender's whole context (absent basis = ours, absent ov = none)
  //   basis     the parsed basis, or null (absent or unreadable)
  //   overrides the parsed overrides, or null (absent or nothing usable)
  //   unread    the parts that were present but could not be read: "basis", "ov"
  // What a reader does with an unread part is the reader's call; this only says what the link holds.
  function readValueContext(params) {
    const get = name => {
      if (!params) return null;
      const v = typeof params.get === "function" ? params.get(name) : params[name];
      return v === undefined || v === null ? null : String(v);
    };
    const basisText = get("basis");
    const ovText = get("ov");
    const complete = get("valuecontext") === "1";
    const basis = parseBasisParam(basisText);
    const overrides = parseOvParam(ovText);
    const unread = [];
    if (basisText && !basis) unread.push("basis");
    if (ovText && !overrides) unread.push("ov");
    return {present: Boolean(complete || basisText || ovText), complete, basisText, ovText, basis, overrides, unread};
  }

  return {
    BASIS_KEYS, PACK_AFTER, OVERRIDE_MIN, OVERRIDE_MAX,
    normalizeEntry, isAdjustment, clampWeight,
    packOverrides, unpackOverrides, packOverridesWithTypes, unpackOverridesWithTypes,
    formatBasisParam, formatOvParam, parseBasisParam, parseOvParam, readValueContext,
  };
});
