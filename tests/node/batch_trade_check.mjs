// JEG-1036: unit tests for batch trade discovery (mcp/batch.ts).
// Run by tests/test_mcp_remote.py or directly: node tests/node/batch_trade_check.mjs
import assert from "node:assert/strict";
import { findTradesLeague } from "../../supabase/functions/mcp/batch.ts";

const settings = { scoring: "ppr", teams: 12, superflex: 0 };

// ---------- stub findTradesForPair ----------
// Returns predictable trades based on roster contents.
function makePairStub(tradesByOpponent) {
  return async (_settings, _mine, theirRoster, _opts) => {
    // Use the first player name on their roster as a lookup key.
    const key = theirRoster[0] || "__empty__";
    return tradesByOpponent[key] || { trades: [], unmatchedMine: [], unmatchedTheirs: [] };
  };
}

// ---------- helpers ----------
function trade(given, received, givenKeys, receivedKeys, myLineup, oppMarket, reasons = []) {
  return {
    given, received, givenKeys, receivedKeys,
    myValueEdge: myLineup * 0.8,
    opponentMarketEdge: oppMarket,
    myLineupPointChange: myLineup,
    reasons,
  };
}

// ---------- test: basic merge from two opponents ----------
{
  const stub = makePairStub({
    "Opp1-Player": {
      trades: [trade(["MyRB"], ["Opp1WR"], [1], [10], 5.0, 2.0, ["natural fit"])],
      unmatchedMine: [], unmatchedTheirs: [],
    },
    "Opp2-Player": {
      trades: [trade(["MyWR"], ["Opp2RB"], [2], [20], 3.0, 1.5, ["upgrade"])],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["MyRB", "MyWR"],
    [
      { name: "Team Alpha", roster: ["Opp1-Player"] },
      { name: "Team Beta", roster: ["Opp2-Player"] },
    ],
    stub,
  );

  assert.equal(result.trades.length, 2, "should find 2 trades");
  assert.equal(result.trades[0].myLineupPointChange, 5.0, "best trade first");
  assert.equal(result.trades[0].opponent, "Team Alpha");
  assert.equal(result.trades[1].opponent, "Team Beta");
  assert.equal(result.duplicatesRemoved, 0);
  assert.equal(result.perOpponent.length, 2);
  console.log("PASS: basic merge from two opponents");
}

// ---------- test: dedup same player sets across opponents ----------
{
  // Same trade (keys [1]->[10]) found against two opponents; keep the better one.
  const stub = makePairStub({
    "OppA": {
      trades: [trade(["MyRB"], ["TheirWR"], [1], [10], 4.0, 2.0)],
      unmatchedMine: [], unmatchedTheirs: [],
    },
    "OppB": {
      trades: [trade(["MyRB"], ["TheirWR"], [1], [10], 6.0, 1.0)],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["MyRB"],
    [
      { name: "Team A", roster: ["OppA"] },
      { name: "Team B", roster: ["OppB"] },
    ],
    stub,
  );

  assert.equal(result.trades.length, 1, "dedup removes duplicate");
  assert.equal(result.trades[0].myLineupPointChange, 6.0, "keeps the better trade");
  assert.equal(result.trades[0].opponent, "Team B");
  assert.equal(result.duplicatesRemoved, 1);
  console.log("PASS: dedup same player sets across opponents");
}

// ---------- test: dedup same trade both directions ----------
{
  // Trade A: I give [1] for [10]. Trade B: I give [10] for [1] (reverse).
  const stub = makePairStub({
    "OppX": {
      trades: [
        trade(["PlayerA"], ["PlayerB"], [1], [10], 3.0, 1.0),
        trade(["PlayerB"], ["PlayerA"], [10], [1], 1.0, 4.0),
      ],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["PlayerA", "PlayerB"],
    [{ name: "Team X", roster: ["OppX"] }],
    stub,
  );

  assert.equal(result.trades.length, 1, "reverse-direction dedup");
  assert.equal(result.trades[0].myLineupPointChange, 3.0, "keeps the better direction");
  assert.equal(result.duplicatesRemoved, 1);
  console.log("PASS: dedup same trade both directions");
}

// ---------- test: ranking filters out negative trades ----------
{
  const stub = makePairStub({
    "OppY": {
      trades: [
        trade(["A"], ["B"], [1], [2], -2.0, 3.0),   // negative for me
        trade(["C"], ["D"], [3], [4], 5.0, -1.0),    // negative for opponent
        trade(["E"], ["F"], [5], [6], 4.0, 2.0),     // good for both
      ],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["A", "C", "E"],
    [{ name: "Rival", roster: ["OppY"] }],
    stub,
  );

  assert.equal(result.trades.length, 1, "only trades good for both sides");
  assert.equal(result.trades[0].given[0], "E");
  assert.equal(result.trades[0].received[0], "F");
  console.log("PASS: ranking filters out negative trades");
}

// ---------- test: ranking order ----------
{
  const stub = makePairStub({
    "OppZ": {
      trades: [
        trade(["A"], ["B"], [1], [2], 3.0, 2.0),
        trade(["C"], ["D"], [3], [4], 7.0, 1.0),
        trade(["E"], ["F"], [5], [6], 5.0, 3.0),
      ],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["A", "C", "E"],
    [{ name: "Z", roster: ["OppZ"] }],
    stub,
  );

  assert.equal(result.trades.length, 3);
  assert.deepEqual(
    result.trades.map((t) => t.myLineupPointChange),
    [7.0, 5.0, 3.0],
    "sorted by my lineup point change descending",
  );
  console.log("PASS: ranking order");
}

// ---------- test: limit caps output ----------
{
  const trades = [];
  for (let i = 0; i < 30; i++) {
    trades.push(trade([`P${i}`], [`Q${i}`], [i], [100 + i], 10 - i * 0.1, 1.0));
  }
  const stub = makePairStub({
    "Opp": { trades, unmatchedMine: [], unmatchedTheirs: [] },
  });

  const result = await findTradesLeague(
    settings,
    ["mine"],
    [{ name: "Big", roster: ["Opp"] }],
    stub,
    { limit: 5 },
  );

  assert.equal(result.trades.length, 5, "limit caps at 5");
  assert.equal(result.total, 30, "total reports all qualifying");
  console.log("PASS: limit caps output");
}

// ---------- test: unmatched names reported per opponent ----------
{
  const stub = makePairStub({
    "OppU": {
      trades: [],
      unmatchedMine: ["BadName1"],
      unmatchedTheirs: ["BadName2"],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["mine"],
    [{ name: "UnmatchTeam", roster: ["OppU"] }],
    stub,
  );

  assert.equal(result.perOpponent[0].unmatchedNames.length, 2);
  assert.ok(result.perOpponent[0].unmatchedNames[0].includes("(mine)"));
  assert.ok(result.perOpponent[0].unmatchedNames[1].includes("(UnmatchTeam)"));
  console.log("PASS: unmatched names reported per opponent");
}

// ---------- test: empty roster skipped gracefully ----------
{
  let called = false;
  const stub = async () => { called = true; return { trades: [], unmatchedMine: [], unmatchedTheirs: [] }; };

  const result = await findTradesLeague(
    settings,
    ["mine"],
    [{ name: "EmptyTeam", roster: [] }],
    stub,
  );

  assert.equal(called, false, "pair finder not called for empty roster");
  assert.equal(result.perOpponent[0].tradesFound, 0);
  console.log("PASS: empty roster skipped gracefully");
}

// ---------- negative tests: guards ----------
{
  const noop = async () => ({ trades: [], unmatchedMine: [], unmatchedTheirs: [] });

  // Empty mine roster
  await assert.rejects(
    () => findTradesLeague(settings, [], [{ name: "X", roster: ["a"] }], noop),
    /mine roster is empty/,
  );
  console.log("PASS: guard - empty mine roster");

  // Empty opponents list
  await assert.rejects(
    () => findTradesLeague(settings, ["a"], [], noop),
    /opponents list is empty/,
  );
  console.log("PASS: guard - empty opponents list");

  // Too many opponents
  const tooMany = Array.from({ length: 16 }, (_, i) => ({ name: `T${i}`, roster: ["p"] }));
  await assert.rejects(
    () => findTradesLeague(settings, ["a"], tooMany, noop),
    /too many opponents/,
  );
  console.log("PASS: guard - too many opponents");
}

// ---------- test: simpler trades preferred at same lineup change ----------
{
  const stub = makePairStub({
    "Opp": {
      trades: [
        trade(["A", "B"], ["C", "D"], [1, 2], [3, 4], 5.0, 2.0),  // 4 players
        trade(["E"], ["F"], [5], [6], 5.0, 2.0),                    // 2 players
      ],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["A", "B", "E"],
    [{ name: "S", roster: ["Opp"] }],
    stub,
  );

  assert.equal(result.trades[0].given.length, 1, "simpler trade ranked first");
  console.log("PASS: simpler trades preferred at same lineup change");
}

// ---------- test: dedup with unsorted keys ----------
{
  // Keys in different order should still dedup.
  const stub = makePairStub({
    "OppA": {
      trades: [trade(["X", "Y"], ["Z"], [2, 1], [10], 4.0, 1.0)],
      unmatchedMine: [], unmatchedTheirs: [],
    },
    "OppB": {
      trades: [trade(["Y", "X"], ["Z"], [1, 2], [10], 3.0, 2.0)],
      unmatchedMine: [], unmatchedTheirs: [],
    },
  });

  const result = await findTradesLeague(
    settings,
    ["X", "Y"],
    [
      { name: "A", roster: ["OppA"] },
      { name: "B", roster: ["OppB"] },
    ],
    stub,
  );

  assert.equal(result.trades.length, 1, "unsorted keys still dedup");
  assert.equal(result.trades[0].myLineupPointChange, 4.0, "keeps better");
  assert.equal(result.duplicatesRemoved, 1);
  console.log("PASS: dedup with unsorted keys");
}

console.log("\nAll batch trade tests passed.");
