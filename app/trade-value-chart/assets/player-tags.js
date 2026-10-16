/**
 * Start / Hold / Stash / Drop tags (JEG-571, part of JEG-521 G5).
 *
 * A pure function of fields every priced row already carries from the engine
 * (ES-10): `ddfTier` ("starter" | "bench" | "waiver", read off the roster
 * convention, so the starter count follows the reader's league and never a
 * hard-coded number), `startWorthy` (P(level above the starter line)) and
 * `lineupShare`. No value path is touched.
 *
 * Definitions (defaults chosen 2026-10-12, recorded on JEG-571; Jeremy can
 * overrule, they are copy and methodology):
 *   Start = inside the starter tier on the reader's settings.
 *   Stash = not a starter, but P(projected to start) >= STASH_START_PROBABILITY.
 *   Drop  = at or below the waiver line (the best freely available alternative)
 *           and not a Stash.
 *   Hold  = rostered, not Start, Stash or Drop (the bench tier).
 * A row with no tier (no included source prices him) has no tag (null).
 *
 * The handcuff contingency (JEG-526) and waiver upside as the bar (JEG-529)
 * are parked; when they land they change the Stash and Drop tests here.
 */
(function (exports) {
  "use strict";

  var STASH_START_PROBABILITY = 0.25;
  var TAGS = ["Start", "Hold", "Stash", "Drop"];

  function finite(x) { return typeof x === "number" && isFinite(x); }

  function playerTag(row, options) {
    if (!row) return null;
    var threshold = options && finite(options.stashStartProbability)
      ? options.stashStartProbability : STASH_START_PROBABILITY;
    var tier = row.ddfTier;
    if (tier === "starter") return "Start";
    if (tier !== "bench" && tier !== "waiver") return null;
    if (finite(row.startWorthy) && row.startWorthy >= threshold) return "Stash";
    return tier === "bench" ? "Hold" : "Drop";
  }

  exports.PlayerTags = {
    TAGS: TAGS,
    STASH_START_PROBABILITY: STASH_START_PROBABILITY,
    playerTag: playerTag
  };
})(typeof module !== "undefined" && module.exports ? module.exports : (this.window = this.window || {}));
