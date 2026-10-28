## 2026-10-27 - JEG-1043: "Show viable offers only" and starters at the positions given up

Contract: per Jeremy's "A" (2026-10-27), build items 1 and 2 of JEG-1043 on Find a trade: your team. Item 1 is a "Show viable offers only" toggle. Item 2 is per-offer starters before and after at each position a side gives up. The package panel and the guardrails were split into JEG-1183 and JEG-1184. Session `session:fe-cloud`, branch `fe/JEG-1043`.

Changed (`app/v2/finder.js`, `app/v2/v2.css`):
- A toggle above the results: "Show viable offers only (N of M groups)". When ticked, the list keeps only the groups whose best package has a viability label (JEG-1108's `viabilityLabel`, via the new `viabilityFor`). The ranking and the top-10 limit are unchanged. When no group is viable, the PMM doc's empty state shows ("No slam dunks with this team…"). The toggle appears only when the fit context exists, which is the same condition as the viability label.
- Each card's lineup block adds one line per side: "Your starters at the positions you give up: RB A, B, C → B, C; …" and "Their starters at the positions they give up: …". The lines use the DDF Value lineup, and FLEX starters count at their own position.
- Each card carries `data-find-viable`, the label for the current selection.
- New pure helpers, exported: `startersAtGivenPositions`, `givenPositionsLine`, `viableGroups`.

Deviation: the ticket's "your starters at protected positions" depends on protected positions, which arrive with JEG-1184 (guardrails). Until then the "you" line covers the positions you give up.

Finding: on this week's data, every group the search lists at its best package is viable. The search already requires a DDF Value win and chart agreement, and the default keep-lineup boxes stop empty slots. So the toggle removes groups only in cases like the keep-lineup boxes being off and a package taking the other team's only QB.

### Verified (check named)
- `tests.test_v2_finder_viable` (node unit; in test-core and its shard): the helpers pass, and 4 mutations are caught.
- `tests.test_v2_finder_viable_render` (render; in test-unit): toggle, filtering, the empty state and the given-positions lines at 1366, 390 and 320. On this week's data the fixture gives 3 of 5 groups viable, and 3 render mutations are caught. Both tests fail on main, which has no toggle and no helpers.

### Claimed, not confirmed
- Live check after deploy (see JEG-1043).
