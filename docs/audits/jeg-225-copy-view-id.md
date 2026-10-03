# JEG-225 internal view-ID copy-test false positive

The public-copy scanner rejected the internal"vorp" ID in VIEW_MODE_ORDER
although the visible tab uses Value above waivers. A narrow exemption now
recognizes only that exact standalone declaration line. A visible lowercase
or uppercase VORP label elsewhere still fails, including one appended on the
same line. Existing internal source IDs and template-copy handling remain.
The exemption deliberately fails closed if the enum declaration is reformatted
or changed. No runtime code, ID, value, or public wording changed.

Branchcodex/jeg-225-internal-view-id is stacked on JEG-221's
codex/indexed-default-guard. Integrate the chart guard first, then this test
repair (or review both changes together). No main merge/deployment performed.

Validation: `python3 -m unittest tests.test_public_copy_no_vorp`4 tests,exit0;
`git diff --check`exit0; `make validate`exit0 with existing skips on the combined
JEG-221/225 working branch. Generated timestamp/module outputs were discarded
from this test-only commit. Independent Claude Code MCP review reran the4 tests
and found no required change. Negative cases discriminate a blanket exemption.
Roman owns integration and production verification before parent Done.
