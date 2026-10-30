// Trade Value v2 — trade package constraints (JEG-1262, part of JEG-1183).
//
// A package is a set of trades that are ALREADY chosen, each between "my team" and one other team in the league. This
// file only checks that the set can happen together and, when it can, applies it to the rosters. It does not search,
// select or rank packages, and it never reads a value, a lineup or a fit: it moves roster entries and nothing else.
//
//   TradePackageConstraints.validatePackage(league, trades) -> {ok: true, errors: [], moves} | {ok: false, errors, moves: []}
//   TradePackageConstraints.applyPackage(league, trades)    -> {ok: true, errors: [], league, moves} | {ok: false, errors}
//   TradePackageConstraints.applyTrade(league, trade)       -> applyPackage(league, [trade])
//   TradePackageConstraints.CODES                            -> every error code below
//
// Inputs (the shapes already used by workspace.js and opportunities.js, read as they are):
//   league = {myTeamId, teams: [{id, name?, entries: [{key, name, pos, team?, slot?}]}]}  (a saved workspace passes as is)
//   trade  = {opponentId, give: [ref], receive: [ref]}  (an opportunities.js row passes as is)
//     give    = players leaving my team for the opponent; receive = players leaving the opponent for my team.
//     ref     = a key string, a roster entry {key}, or an engine row {player_key}. Keys compare as strings, as in
//               workspace.js. A ref that carries both key and player_key with different values is ambiguous.
//
// Rules (each one returns an explicit error; nothing is ever applied in part):
//   * my team is in the league; team ids are unique; every roster entry has a key; a key sits on one roster, once;
//   * every trade names a counterparty that is in the league, is not my team, and appears in no other trade;
//   * every trade moves at least one player; one side may be empty and the sides may have different counts;
//   * every player is used at most once across the whole package (both sides, every trade);
//   * every given player is on my original roster; every received player is on that counterparty's original roster.
//
// Applying: trades are applied one after another in the order given. A team keeps its remaining entries in their
// original order and the arriving entries follow, in trade order. Every entry is the roster's own entry, copied
// unchanged (key, name, pos, team and slot): identity is conserved and nothing is priced. A "x:" key (K, DEF, or a
// player with no chart row) moves like any other. A slot travels as recorded; this file never re-decides a lineup.
// The result's league holds only myTeamId and the teams (copies), so it can be fed back in for the next trade.
// Inputs are never modified.
(function (root) {
  "use strict";

  const CODES = Object.freeze({
    BAD_LEAGUE: "bad_league",                       // league is not an object with a teams array
    BAD_TEAM: "bad_team",                           // a team is not an object, has no id, or its entries are not an array
    DUPLICATE_TEAM_ID: "duplicate_team_id",         // two teams share an id
    NO_MY_TEAM: "no_my_team",                       // myTeamId is missing or names no team
    MISSING_ROSTER_KEY: "missing_roster_key",       // a roster entry has no usable key
    DUPLICATE_ROSTER_KEY: "duplicate_roster_key",   // a key sits on two rosters, or twice on one: its holder is ambiguous
    BAD_PACKAGE: "bad_package",                     // trades is not an array
    BAD_TRADE: "bad_trade",                         // a trade is not an object, or give/receive is not an array
    MISSING_COUNTERPARTY: "missing_counterparty",   // a trade names no opponentId
    UNKNOWN_COUNTERPARTY: "unknown_counterparty",   // opponentId names no team in the league
    SELF_TRADE: "self_trade",                       // opponentId is my team
    DUPLICATE_COUNTERPARTY: "duplicate_counterparty", // two trades name the same counterparty
    EMPTY_TRADE: "empty_trade",                     // a trade moves no player
    MISSING_PLAYER_KEY: "missing_player_key",       // a ref has no usable key
    AMBIGUOUS_PLAYER_KEY: "ambiguous_player_key",   // a ref carries key and player_key that disagree
    DUPLICATE_PLAYER: "duplicate_player",           // a player is used twice in the package
    NOT_ON_ROSTER: "not_on_roster",                 // a moved player is not on the original roster of the side sending him
  });

  const isObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  // A usable key is a non-empty string or a finite number, read as a string (workspace.js stores String(entry.key)).
  const asKey = value => {
    if (typeof value === "string") return value.trim() ? value : null;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
    return null;
  };
  const has = (obj, prop) => Object.prototype.hasOwnProperty.call(obj, prop) && obj[prop] !== undefined && obj[prop] !== null;

  // {key} | {error: code}
  function refKey(ref) {
    if (!isObject(ref)) {
      const key = asKey(ref);
      return key === null ? {error: CODES.MISSING_PLAYER_KEY} : {key};
    }
    const a = has(ref, "key") ? asKey(ref.key) : null;
    const b = has(ref, "player_key") ? asKey(ref.player_key) : null;
    if ((has(ref, "key") && a === null) || (has(ref, "player_key") && b === null)) return {error: CODES.MISSING_PLAYER_KEY};
    if (a !== null && b !== null && a !== b) return {error: CODES.AMBIGUOUS_PLAYER_KEY};
    const key = a !== null ? a : b;
    return key === null ? {error: CODES.MISSING_PLAYER_KEY} : {key};
  }

  // The league read once: team by id and the one holder of every key. Errors here mean no trade can be judged.
  function readLeague(league) {
    const errors = [];
    if (!isObject(league) || !Array.isArray(league.teams)) return {errors: [{code: CODES.BAD_LEAGUE, message: "league needs a teams array"}]};
    const teams = new Map();
    const holder = new Map();
    league.teams.forEach((team, teamIndex) => {
      const id = isObject(team) ? asKey(team.id) : null;
      if (id === null || !Array.isArray(team.entries)) {
        errors.push({code: CODES.BAD_TEAM, teamIndex, message: `team ${teamIndex} needs an id and an entries array`});
        return;
      }
      if (teams.has(id)) {
        errors.push({code: CODES.DUPLICATE_TEAM_ID, teamId: id, message: `two teams share the id ${id}`});
        return;
      }
      teams.set(id, team);
      team.entries.forEach((entry, entryIndex) => {
        const key = isObject(entry) && has(entry, "key") ? asKey(entry.key) : null;
        if (key === null) {
          errors.push({code: CODES.MISSING_ROSTER_KEY, teamId: id, entryIndex, message: `entry ${entryIndex} on team ${id} has no key`});
          return;
        }
        if (holder.has(key)) {
          const first = holder.get(key).teamId;
          errors.push({code: CODES.DUPLICATE_ROSTER_KEY, key, teamId: id, otherTeamId: first,
            message: first === id ? `${key} is on team ${id} twice` : `${key} is on both team ${first} and team ${id}`});
          return;
        }
        holder.set(key, {teamId: id, entry});
      });
    });
    const mine = isObject(league) ? asKey(league.myTeamId) : null;
    if (mine === null || !teams.has(mine)) errors.push({code: CODES.NO_MY_TEAM, message: "myTeamId must name a team in the league"});
    return {errors, teams, holder, mine};
  }

  function validatePackage(league, trades) {
    const read = readLeague(league);
    const errors = read.errors.slice();
    if (!Array.isArray(trades)) errors.push({code: CODES.BAD_PACKAGE, message: "trades must be an array"});
    if (errors.length) return {ok: false, errors, moves: []};
    const {teams, holder, mine} = read;
    const counterparties = new Map();
    const used = new Map();
    const moves = [];
    trades.forEach((trade, tradeIndex) => {
      if (!isObject(trade) || !Array.isArray(trade.give) || !Array.isArray(trade.receive)) {
        errors.push({code: CODES.BAD_TRADE, tradeIndex, message: `trade ${tradeIndex} needs give and receive arrays`});
        return;
      }
      const opp = has(trade, "opponentId") ? asKey(trade.opponentId) : null;
      if (opp === null) errors.push({code: CODES.MISSING_COUNTERPARTY, tradeIndex, message: `trade ${tradeIndex} names no counterparty`});
      else if (opp === mine) errors.push({code: CODES.SELF_TRADE, tradeIndex, teamId: opp, message: `trade ${tradeIndex} is with my own team`});
      else if (!teams.has(opp)) errors.push({code: CODES.UNKNOWN_COUNTERPARTY, tradeIndex, teamId: opp, message: `trade ${tradeIndex} names ${opp}, which is not in the league`});
      else if (counterparties.has(opp)) {
        errors.push({code: CODES.DUPLICATE_COUNTERPARTY, tradeIndex, teamId: opp, otherTradeIndex: counterparties.get(opp),
          message: `trades ${counterparties.get(opp)} and ${tradeIndex} are both with ${opp}`});
      } else counterparties.set(opp, tradeIndex);
      if (!trade.give.length && !trade.receive.length) errors.push({code: CODES.EMPTY_TRADE, tradeIndex, message: `trade ${tradeIndex} moves no player`});
      [["give", mine, opp], ["receive", opp, mine]].forEach(([side, from, to]) => {
        trade[side].forEach((ref, refIndex) => {
          const at = {tradeIndex, side, refIndex};
          const r = refKey(ref);
          if (r.error) {
            errors.push({code: r.error, ...at, message: `trade ${tradeIndex} ${side} ${refIndex}: ${r.error === CODES.AMBIGUOUS_PLAYER_KEY ? "key and player_key disagree" : "no key"}`});
            return;
          }
          const key = r.key;
          if (used.has(key)) {
            const prev = used.get(key);
            errors.push({code: CODES.DUPLICATE_PLAYER, key, ...at, other: prev, message: `${key} is used in trade ${prev.tradeIndex} ${prev.side} and again in trade ${tradeIndex} ${side}`});
            return;
          }
          used.set(key, at);
          const held = holder.get(key);
          if (from === null || !teams.has(from) || !held || held.teamId !== from) {
            errors.push({code: CODES.NOT_ON_ROSTER, key, ...at, expectedTeamId: from, actualTeamId: held ? held.teamId : null,
              message: `${key} is not on ${from === mine ? "my" : `team ${from}'s`} roster${held ? ` (it is on team ${held.teamId})` : ""}`});
            return;
          }
          moves.push({key, from, to, tradeIndex, side});
        });
      });
    });
    return errors.length ? {ok: false, errors, moves: []} : {ok: true, errors: [], moves};
  }

  function applyPackage(league, trades) {
    const check = validatePackage(league, trades);
    if (!check.ok) return {ok: false, errors: check.errors};
    const mine = asKey(league.myTeamId);
    const teams = league.teams.map(team => ({...clone(team), id: asKey(team.id)}));
    const byId = new Map(teams.map(team => [team.id, team]));
    // One trade at a time, exactly as the package is read. Each side loses its leaving keys and gains the other side's entries.
    trades.forEach((trade, tradeIndex) => {
      const opp = asKey(trade.opponentId);
      const out = check.moves.filter(m => m.tradeIndex === tradeIndex && m.side === "give").map(m => m.key);
      const back = check.moves.filter(m => m.tradeIndex === tradeIndex && m.side === "receive").map(m => m.key);
      const a = byId.get(mine);
      const b = byId.get(opp);
      const take = (team, keys) => keys.map(key => team.entries.find(e => asKey(e.key) === key));
      const leavingA = take(a, out);
      const leavingB = take(b, back);
      a.entries = a.entries.filter(e => !out.includes(asKey(e.key))).concat(leavingB);
      b.entries = b.entries.filter(e => !back.includes(asKey(e.key))).concat(leavingA);
    });
    return {ok: true, errors: [], league: {myTeamId: mine, teams}, moves: check.moves};
  }

  const applyTrade = (league, trade) => applyPackage(league, [trade]);

  const api = {CODES, validatePackage, applyPackage, applyTrade};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradePackageConstraints = api;
})(typeof window !== "undefined" ? window : globalThis);
