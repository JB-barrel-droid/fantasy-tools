"""JEG-133 scratch exercise A: deliberately red build.

This test always fails. The deploy gate must catch the red `make validate`
and block the Pages deploy, even though the HEAD commit touches only
dist/modules/ (the old path-conditional bypass).
"""
def test_scratch_red_build():
    assert False, "JEG-133 scratch exercise A: deliberate red build"
