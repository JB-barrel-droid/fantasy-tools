# Curve Widget Guard Harness

`tools/guard_harness.mjs` runs the browser curve-widget guard math in Node
against `data/fixtures/current/`, without a browser or deploy.

The harness loads the real `value-model.js` and `curve-widget.js`, supplies a
small DOM shim, waits for the widget init path, then calls the widget's exposed
test hook. It does not reimplement the guard economics.

Useful commands:

```bash
node tools/guard_harness.mjs
node tools/guard_harness.mjs --json
node tools/guard_harness.mjs --assert-good
node tools/guard_harness.mjs --simulate tier-mismatch --assert-bad
```

`--simulate tier-mismatch` reproduces the JEG-5 broken state: live adjustment
cells are applied using the source's published-value tiers instead of the DDF
training tiers. `make validate` runs both the known-good current fixture path
and this known-bad current fixture simulation.

The original production JEG-5 diagnostic was recorded against the fixture from
commit `5372f7b`. To verify that historical number exactly, export that fixture
to a temporary directory and run the recorded assertion:

```bash
mkdir -p /tmp/jeg5-fixture
git show 5372f7b:data/fixtures/current/comparison-sources-data.json >/tmp/jeg5-fixture/comparison-sources-data.json
git show 5372f7b:data/fixtures/current/players.json >/tmp/jeg5-fixture/players.json
node tools/guard_harness.mjs --fixture-dir /tmp/jeg5-fixture --simulate tier-mismatch --assert-jeg5-recorded
```

That historical check reproduces ESPN `782.719965` vs `862.62`, delta
`-79.900035`, display scale `2.5701`, 118 players, 8 live cells, 8 baked cells,
and the recorded per-position breakdown.
