"""First-token nickname expansion table for canonical player identity.

Vendored from lottery/bin/identity.py (NICKNAMES) on 2026-09-22 so the
repo-owned players.json bake is self-contained for GitHub Actions — the
bake must not import from ~/workspace paths.

DRIFT RULE: this table MUST stay byte-identical to the source. The
regression test tests/test_identity_drift.py fails loudly on any drift;
update both copies together, never one alone.
"""

NICKNAMES = {
    "cam": "cameron", "kenny": "kenneth", "mike": "michael",
    "alex": "alexander", "ben": "benjamin", "chris": "christopher",
    "dan": "daniel", "doug": "douglas", "greg": "gregory",
    "jeff": "jeffrey", "jim": "james", "jimmy": "james", "joe": "joseph",
    "josh": "joshua", "matt": "matthew", "nate": "nathan",
    "nick": "nicholas", "rob": "robert", "sam": "samuel",
    "steve": "steven", "tim": "timothy", "tom": "thomas", "tony": "anthony",
    "will": "william", "zack": "zachary", "zac": "zachary",
    "pat": "patrick", "andy": "andrew", "drew": "andrew",
    "ed": "edward", "ted": "theodore", "rick": "richard",
    "bill": "william", "bobby": "robert", "bob": "robert",
    "charlie": "charles", "chuck": "charles", "dave": "david",
    "don": "donald", "ron": "ronald", "ken": "kenneth",
    "terry": "terrance",
    # Monikers consolidated from the old loaders/fantasypros.py private
    # ALIASES (2026-09-18 canonical migration): "hollywood brown" was mapped
    # to "marquise brown" there; "scotty miller" to "scott miller".
    # First-token keyed like the rest of the table.
    "hollywood": "marquise", "scotty": "scott",
}
