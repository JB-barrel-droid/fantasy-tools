"""GAP-USAT-RELAY-ANON (2026-10-09): the usatoday-fetch Edge Function is a
service-role-only, allowlisted relay, not a fetch proxy for the anon key.

The deployed function is supabase/functions/usatoday-fetch/index.ts (deployed
with verify_jwt true). Static checks; the live behaviour (anon and publishable
keys refused with 403) is checked by hand at deploy time and recorded in the
risk register.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "supabase" / "functions" / "usatoday-fetch" / "index.ts").read_text(encoding="utf-8")
CALLER = (ROOT / "ops" / "watchdog" / "pull_usatoday.py").read_text(encoding="utf-8")


class RelaySource(unittest.TestCase):
    def test_service_role_is_required_before_any_fetch(self):
        self.assertIn('callerRole(req) !== "service_role"', SRC)
        self.assertLess(SRC.index('callerRole(req) !== "service_role"'), SRC.index("await fetch("))

    def test_hosts_are_the_usatoday_set_with_path_rules(self):
        hosts = set(re.findall(r'^\s*"([a-z0-9.-]+)":\s*\[', SRC, re.M))
        self.assertEqual({"www.usatoday.com", "usatoday.com", "amp.usatoday.com", "www.gannett-cdn.com"}, hosts)

    def test_redirects_are_checked_hop_by_hop(self):
        self.assertIn('redirect: "manual"', SRC)
        self.assertNotIn('redirect: "follow"', SRC)
        self.assertIn("allowed(new URL(location, target)", SRC)

    def test_the_ingest_sends_the_service_key(self):
        self.assertIn('os.environ.get("SUPABASE_SERVICE_KEY"', CALLER)
        self.assertIn('"Authorization": "Bearer " + key', CALLER)


if __name__ == "__main__":
    unittest.main()
