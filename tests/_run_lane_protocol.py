#!/usr/bin/env python3
"""Run the lane protocol tests and capture output to a file."""
import sys
import unittest
import io
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Capture all test output to a buffer so we can save it.
buf = io.StringIO()
loader = unittest.TestLoader()
suite = loader.loadTestsFromName("tests.test_lane_protocol")
runner = unittest.TextTestRunner(verbosity=2, stream=buf)
result = runner.run(suite)

# Save captured output to a file in the repo.
out_path = REPO / "tests" / "_lane_protocol_test_output.txt"
with open(out_path, "w") as f:
    f.write(buf.getvalue())
    f.write("\n")
    f.write(f"was_successful={result.wasSuccessful()}\n")
    f.write(f"errors={len(result.errors)}\n")
    f.write(f"failures={len(result.failures)}\n")
    f.write(f"tests_run={result.testsRun}\n")

print(f"Output written to {out_path}")
print(f"Success: {result.wasSuccessful()}")
sys.exit(0 if result.wasSuccessful() else 1)