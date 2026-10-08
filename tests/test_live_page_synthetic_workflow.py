"""Behaviour tests for .github/workflows/live-page-synthetic.yml's monitor-bridge.

Defect (found on the 2026-10-03 05:53 CDT scheduled run 37117867195): the
`live-gate` job PASSED but the run reported failure, because the
`monitor-bridge` step `Validate and prepare monitor artifact` died with
`KeyError: 'generated_at'`. Root cause: producer/consumer schema mismatch --
`tests/rendered_gate/live.mjs` writes camelCase `generatedAt`, the bridge read
snake_case `generated_at`. Net effect: the daily live-page check showed RED on
the monitor while the page was fine, and the monitor never received fresh
synthetic-gate results.

These tests do not just read the YAML: they extract the real `run:` script and
execute it against producer-shaped reports. Every rule is negative-tested,
including a discrimination run proving the pre-fix script fails on the same
input the fixed script handles.
"""
import json
import re
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/live-page-synthetic.yml").read_text(encoding="utf-8")

STEP = "Validate and prepare monitor artifact"

# What GitHub's runner interpolates before bash sees the script.
GH_INTERPOLATION = {
    "${{ github.server_url }}": "https://github.com",
    "${{ github.repository }}": "o/r",
    "${{ github.run_id }}": "123",
}

# The exact pre-fix reader line, reintroduced for the discrimination test.
BUGGY_READER = "generated_at = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))"


def step_blocks(text):
    blocks, current = [], None
    for line in text.splitlines():
        if re.match(r"^      - ", line):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None and (line.startswith("        ") or not line.strip()):
            current.append(line)
        elif current is not None:
            blocks.append("\n".join(current))
            current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def find_step(text, name):
    for block in step_blocks(text):
        if re.search(rf"^\s*(- )?name:\s*{re.escape(name)}\s*$", block, re.M):
            return block
    return None


def script_of(block):
    lines = block.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)run:\s*\|\s*$", line)
        if m:
            indent = len(m.group(1)) + 2
            body = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) < indent:
                    break
                body.append(nxt[indent:] if len(nxt) >= indent else "")
            return "\n".join(body).rstrip() + "\n"
    return None


def interpolated(script):
    for expr, value in GH_INTERPOLATION.items():
        script = script.replace(expr, value)
    assert "${{" not in script, "uninterpolated GitHub expression left in script"
    return script


def run_bridge(script, report):
    """Run the bridge script in a temp dir holding the given report. Returns (rc, json)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "output"
        out.mkdir()
        if report is not None:
            (out / "live-page-synthetic.json").write_text(json.dumps(report))
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": td}
        r = subprocess.run(["bash", "-e", "-c", script], cwd=td, env=env,
                           capture_output=True, text=True)
        result_path = out / "live-page-synthetic.json"
        data = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
        return r, data


def producer_report(**overrides):
    """A report shaped exactly like tests/rendered_gate/live.mjs emits."""
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "url": "https://example.invalid/",
        "expectedBuilds": ["tv-20261003-0000-abcdef12"],
        "liveTag": "tv-20261003-0000-abcdef12",
        "buildStamp": "tv-20261003-0000-abcdef12",
        "httpStatus": 200,
        "pageErrors": [],
        "problems": [],
        "passed": True,
    }
    report.update(overrides)
    return report


class LivePageSyntheticBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        block = find_step(WORKFLOW, STEP)
        assert block is not None, f"step {STEP!r} missing from workflow"
        cls.script = interpolated(script_of(block))
        assert cls.script, f"step {STEP!r} has no run block"

    def test_camelcase_report_is_accepted_and_green(self):
        """The real producer shape (generatedAt): exit 0, monitor green, run metadata set."""
        r, data = run_bridge(self.script, producer_report())
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(data["monitor"]["status"], "green")
        self.assertTrue(data["monitor"]["freshness"]["is_fresh"])
        self.assertEqual(data["run_id"], "123")
        self.assertEqual(data["run_url"], "https://github.com/o/r/actions/runs/123")

    def test_snake_case_report_still_accepted(self):
        """Legacy fallback paths write generated_at; the reader tolerates both."""
        report = producer_report()
        del report["generatedAt"]
        report["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        r, data = run_bridge(self.script, report)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(data["monitor"]["status"], "green")

    def test_stale_report_is_marked_stale(self):
        """A 40-hour-old report keeps the freshness math working: status stale."""
        old = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat().replace("+00:00", "Z")
        r, data = run_bridge(self.script, producer_report(generatedAt=old))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(data["monitor"]["status"], "stale")
        self.assertFalse(data["monitor"]["freshness"]["is_fresh"])

    def test_missing_timestamp_fails_closed(self):
        """No timestamp at all is a corrupt artifact: fail, never guess a status."""
        report = producer_report()
        del report["generatedAt"]
        r, _ = run_bridge(self.script, report)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("neither generatedAt nor generated_at", r.stderr)

    def test_prefixed_script_fails_on_producer_shape(self):
        """Discrimination: the pre-fix reader raises KeyError on the producer's
        camelCase report -- the exact failure from run 37117867195."""
        fixed_reader = (
            "raw_ts = data.get('generatedAt', data.get('generated_at'))\n"
            "if not raw_ts:\n"
            "    raise SystemExit('live-page-synthetic.json has neither generatedAt nor generated_at')\n"
            "generated_at = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00'))"
        )
        self.assertIn(fixed_reader, self.script, "fixed reader block not found in extracted script")
        buggy = self.script.replace(fixed_reader, BUGGY_READER)
        r, _ = run_bridge(buggy, producer_report())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("KeyError", r.stderr)


if __name__ == "__main__":
    unittest.main()
