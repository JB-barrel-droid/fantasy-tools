"""Enable identifiable unittest results only inside the baseline gate wrapper."""
import os
import unittest

if os.environ.get("BASELINE_RED_VERBOSE") == "1":
    _init = unittest.TextTestRunner.__init__

    def _verbose(self, *args, **kwargs):
        # Repo runners use keyword/default verbosity; preserve positional callers.
        if len(args) < 3:
            kwargs["verbosity"] = 2
        _init(self, *args, **kwargs)

    unittest.TextTestRunner.__init__ = _verbose
