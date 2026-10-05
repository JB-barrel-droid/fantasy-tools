"""JEG-381: the versioned consolidated_values loader must match the live schema.

Before 2026-10-05 the loader could not write a single row: rows lacked the
NOT NULL player / detail_locator / bake_id columns, scoring was written as
'half_ppr' (CHECK allows standard/half/full), the upsert conflict target
used player_key (the PK is on player), the bake lookup selected columns
public.bakes does not have, and the transactional RPC was called with the
wrong argument name and without the api schema profile, so it always 404'd
into the non-transactional fallback. Each test below fails on that code.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import load_ddf_leg_to_supabase as L  # noqa: E402

# consolidated_values NOT NULL columns + CHECK values (live schema 2026-10-05).
NOT_NULL = {"player", "source", "season", "week", "scoring", "teams", "qb_variant",
            "view", "value", "detail_locator", "bake_id", "player_key", "bake_uuid"}
PK = ["player", "source", "season", "week", "scoring", "teams", "qb_variant", "view"]
BAKE = "a80c9310-f47e-4d18-ac6f-c74f038bfdf4"


def _leg():
    return {
        "inputs": {"source_tag": "cbsros", "scoring": "half_ppr", "teams": 12,
                   "cbsros_snapshot_date": "2026-09-30"},
        "values": [
            {"player": "Jahmyr Gibbs", "player_norm": "jahmyr gibbs", "player_key": 2227,
             "value": 70.0, "raw_value": 20.36},
            {"player": "Amon-Ra St. Brown", "player_key": 3289, "value": 55.0, "raw_value": 15.1},
        ],
    }


def _dims(scoring="half_ppr"):
    return {"source": "cbsros", "season": 2026, "week": 5, "scoring": scoring,
            "teams": 12, "qb_variant": "qb1"}


class FakeClient:
    def __init__(self):
        self.calls = []

    def rpc(self, function, payload, params="", schema=None):
        self.calls.append(("rpc", function, payload, schema))
        return []

    def get(self, table, params=""):
        self.calls.append(("get", table, params))
        return [{"bake_id": BAKE}]

    def post(self, *a, **k):
        self.calls.append(("post", a, k))
        return []


class LoaderContractTest(unittest.TestCase):
    def rows(self, views=("combo_reindexed", "vorp_indexed"), scoring="half_ppr"):
        rows, _ = L.build_rows(_leg(), _dims(scoring), list(views),
                               "2026-09-30T00:00:00Z", BAKE, leg_label="data/x/leg.json")
        return rows

    def test_rows_carry_every_not_null_column(self):
        for row in self.rows():
            missing = {c for c in NOT_NULL if row.get(c) in (None, "")}
            self.assertFalse(missing, f"{row['view']} row missing {missing}")

    def test_player_is_normalized_name_and_locator_names_the_leg_field(self):
        rows = self.rows()
        self.assertEqual({"jahmyr gibbs", "amonra st brown"}, {r["player"] for r in rows})
        combo = [r for r in rows if r["view"] == "combo_reindexed"][0]
        self.assertEqual("data/x/leg.json#values[0].value", combo["detail_locator"])
        vorp = [r for r in rows if r["view"] == "vorp_indexed"][0]
        self.assertTrue(vorp["detail_locator"].endswith(".raw_value"))

    def test_scoring_maps_to_db_check_values(self):
        self.assertEqual({"half"}, {r["scoring"] for r in self.rows(scoring="half_ppr")})
        self.assertEqual({"full"}, {r["scoring"] for r in self.rows(scoring="ppr")})
        with self.assertRaises(L.LoadError):
            self.rows(scoring="superflex")

    def test_pk_tuples_are_unique_and_conflict_target_is_the_pk(self):
        rows = self.rows()
        keys = [tuple(r[c] for c in PK) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(PK, L.UNIQUE_KEY_COLS.split(","))

    def test_rpc_uses_payload_arg_and_api_schema(self):
        sb = FakeClient()
        self.assertEqual("rpc", L.write_rows(sb, "env", self.rows(), use_rpc=True))
        _, fn, payload, schema = sb.calls[0]
        self.assertEqual("ingest_consolidated_values", fn)
        self.assertEqual("api", schema)
        self.assertEqual({"p_payload"}, set(payload))
        self.assertEqual(4, len(payload["p_payload"]["rows"]))

    def test_bake_lookup_uses_live_bakes_columns(self):
        sb = FakeClient()
        self.assertEqual(BAKE, L.resolve_bake_uuid(sb, "env", "cbsros", None))
        params = sb.calls[0][2]
        self.assertIn("select=bake_id", params)
        self.assertIn("order=ingested_at.desc", params)
        self.assertNotIn("created_at", params)


if __name__ == "__main__":
    unittest.main()
