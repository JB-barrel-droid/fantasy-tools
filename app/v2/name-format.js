// Phone name format (JEG-947, Jeremy 2026-10-23): "Marvin Harrison Jr." -> "Harrison Jr., Marvin".
// Pure and dependency-free so node can unit-test it (tests/test_v2_name_format.js) and the browser can load it.
//   DDFNameFormat.lastFirst(name, pos?) -> string
// Unchanged: one-word names, names already holding a comma, and defenses/teams (pos DST/DEF/D/ST or no first name).
(function (root) {
  "use strict";

  var SUFFIX_RE = /^(jr|sr|ii|iii|iv|v)\.?$/i;
  // A word that starts a multi-word last name when it follows the first name ("Amon-Ra St. Brown", "Jacob De Jesus").
  // Never read at position 0, so the first name "Van" (Van Jefferson) stays a first name.
  var PARTICLE_RE = /^(st\.?|de|del|della|di|da|dos|du|van|von|der|den|la|le|bin|al|el|mc)$/i;
  var TEAM_POS_RE = /^(d\/?st|def|dst)$/i;

  function lastFirst(name, pos) {
    var text = String(name == null ? "" : name).trim().replace(/\s+/g, " ");
    if (!text || text.indexOf(",") !== -1) return text;
    if (pos && TEAM_POS_RE.test(String(pos).trim())) return text;
    var words = text.split(" ");
    var suffix = "";
    if (words.length >= 3 && SUFFIX_RE.test(words[words.length - 1])) suffix = " " + words.pop();
    if (words.length < 2 || (words.length === 2 && SUFFIX_RE.test(words[1]))) return text;   // one word, or "Chris Jr.": no last name to lead with
    var cut = words.length - 1;                                // last name = final word ...
    for (var i = 1; i < words.length - 1; i++) {               // ... or from the first particle after the first name
      if (PARTICLE_RE.test(words[i])) { cut = i; break; }
    }
    return words.slice(cut).join(" ") + suffix + ", " + words.slice(0, cut).join(" ");
  }

  var api = {lastFirst: lastFirst};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFNameFormat = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
