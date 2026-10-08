"""Repository regression tests, importable by the Makefile validation targets."""
import sys

# Pipelines print status marks such as "✓". On Windows a piped or redirected
# stdout is cp1252, so those prints raised UnicodeEncodeError and failed tests
# that pass on Linux (UTF-8). Match Linux for the streams only; file reads still
# have to pass encoding="utf-8" themselves.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower().replace("-", "") != "utf8":
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
