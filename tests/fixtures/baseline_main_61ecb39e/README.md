Frozen copies of the value engine as it was on origin/main at 61ecb39e (JEG-1035, before JEG-1044 added the value
basis). tests/test_basis_overrides_render.py serves these in place of the live engine files and requires the current
engine, on the default basis, to give the same values at every league setting (the default path is byte-identical).

When a later change deliberately changes our default values, re-freeze: copy the engine files from the commit's
parent over these, and say so in docs/claude-log.md. Do not edit them to make a test pass.
