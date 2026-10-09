"""Per-publisher readers for the projection sources of the fidelity pulse (JEG-480).

The trade-chart readers (USA Today, FantasyCalc, FantasyPros, CBS) live in
pipelines/fidelity_pulse.py. Each projection source (espn, cbsros, razzball)
is one module here, `pipelines/fidelity_sources/<source>.py`, exposing exactly
this contract. pipelines/fidelity_pulse.py owns everything else: Supabase
reads, the live chart read, comparison, statuses, the JSON artifact, history
and alerts.

Independence rule: a reader parses the publisher's live page / API itself. It
must NOT import or copy parsing code from the ingest pullers
(pipelines/pull_espn_projections.py, pull_cbs_ros_projections.py,
pull_razzball_ros.py, ops/watchdog/*). Reading them to learn URLs, units and
documented rules (e.g. "half PPR = standard + 0.5 x receptions") is fine; the
rule is then restated here. Use fidelity_pulse.parse_page (stdlib html.parser
table walk) for HTML tables and the given `fetch` (polite, honest UA, one
request per host per second) for every request.

Module contract (module-level names):

    SOURCE: str                  "espn" | "cbsros" | "razzball"
    STORED_TABLE: str            Supabase table, e.g. "cbs_ros_projections"
    SNAPSHOT_COLUMN: str         the table's snapshot-date column, e.g. "cbs_snapshot_date"
    STORED_SELECT: str           PostgREST select list the two functions below need
                                 (must include player_key, SNAPSHOT_COLUMN, created_at)
    CHART_DECIMALS: int          decimals the live chart prints its native values with

    def read_publisher(fetch) -> dict:
        Fetch and parse the publisher's current numbers. Returns
          {"rows": [fidelity_pulse.PubRow, ...],
           "url": str,                       # the main page / API read
           "vintage": "YYYY-MM-DD" | None,   # the publisher's own update date if it prints one
           "dates": {"dateModified": iso|None},
           "notes": [str, ...],              # parse anomalies worth showing
           "error": str | None}              # set (and rows=[]) when the read failed
        PubRow(name, pos, team, values) with values = {grain: printed text},
        grain in "std|1", "half|1", "full|1". The value unit must be the unit
        stored_publisher_values() returns (e.g. per-game points), and the text
        is the number exactly as the publisher printed it, or as computed by
        the publisher's documented rule (then use the full-precision string).

    def stored_publisher_values(row: dict) -> dict[str, float]:
        One stored row -> {grain: value} in the publisher's unit (stage 1).
        A row may carry one scoring or all three; return what it carries.

    def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
        One stored row -> {grain: value} in the chart's native unit (stage 2),
        i.e. what assets/comparison-sources-data.json sources[SOURCE].combos
        [<scoring>_12].native should hold for this player before rounding to
        CHART_DECIMALS. ctx = {"ident": fidelity_pulse.Identity, "now":
        datetime, "season": int}; use it for lookups such as a player's team.

Tests: tests/test_fidelity_<source>.py, hermetic (synthetic HTML/JSON
snippets, a fake fetch), proving the parser reads every scoring, skips
non-numeric cells, and fails loudly (error set) on a page without the
expected tables.
"""
