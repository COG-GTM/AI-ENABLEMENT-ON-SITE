"""Offline tests for rest_client.py: every command builds the right request in --dry-run and never sends.
Run: python -m unittest integrations/test_rest_client.py"""

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rest_client  # noqa: E402

ENV = {
    "JIRA_BASE": "https://jira.example.internal",
    "JIRA_TOKEN": "fake-token-value-for-tests",
    "GITLAB_BASE": "https://gitlab.example.internal",
    "GITLAB_TOKEN": "fake-token-value-for-tests",
    "GITHUB_TOKEN": "fake-token-value-for-tests",
    "ADO_ORG": "https://dev.azure.com/example-org",
    "ADO_PROJECT": "Sensor Node",
    "ADO_TOKEN": "fake-token-value-for-tests",
}


def dry(argv: list[str], extra_env: dict | None = None) -> dict:
    env = {**ENV, **(extra_env or {})}
    out = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
        with mock.patch.object(rest_client.urllib.request, "urlopen", side_effect=AssertionError("network call attempted")):
            rc = rest_client.main(["--dry-run", *argv])
    assert rc == 0
    return json.loads(out.getvalue())


class DryRunTests(unittest.TestCase):
    def test_every_documented_command_dry_runs_and_redacts(self):
        cases = {
            ("jira", "search", "project = SN"): ("GET", "/rest/api/2/search?"),
            ("jira", "issue", "SN-42"): ("GET", "/rest/api/2/issue/SN-42"),
            ("confluence", "search", "space = ENG"): ("GET", "/rest/api/content/search?"),
            ("gitlab", "issues", "123"): ("GET", "/api/v4/projects/123/issues?"),
            ("gitlab", "mrs", "group/project"): ("GET", "/api/v4/projects/group%2Fproject/merge_requests?"),
            ("github", "issues", "owner/repo"): ("GET", "https://api.github.com/repos/owner/repo/issues?"),
            ("ado", "query", "00000000-0000-4000-8000-000000000001"): ("GET", "/Sensor%20Node/_apis/wit/wiql/00000000-0000-4000-8000-000000000001?"),
            ("ado", "workitems", "101,102"): ("GET", "/Sensor%20Node/_apis/wit/workitems?ids=101,102&"),
        }
        self.assertEqual({k[:2] for k in cases}, set(rest_client.COMMANDS), "docs and COMMANDS disagree")
        for (system, action, query), (method, fragment) in cases.items():
            with self.subTest(system=system, action=action):
                r = dry([system, action, query])
                self.assertEqual(r["method"], method)
                self.assertEqual(r["method"], "GET")
                self.assertIsNone(r["body"])
                self.assertIn(fragment, r["url"])
                self.assertTrue(r["url"].startswith("https://"))
                dumped = json.dumps(r)
                self.assertNotIn("fake-token-value-for-tests", dumped)
                self.assertIn("<redacted>", dumped)

    def test_jira_cloud_switches_endpoint_and_basic_auth(self):
        r = dry(["jira", "search", "project = SN"], {"JIRA_EMAIL": "user@example.test"})
        self.assertIn("/rest/api/3/search/jql?", r["url"])

    def test_max_results_is_capped(self):
        r = dry(["jira", "search", "project = SN"])
        self.assertIn(f"maxResults={rest_client.MAX_RESULTS}", r["url"])


class RejectionTests(unittest.TestCase):
    def assert_exits(self, argv, extra_env=None):
        env = {**ENV, **(extra_env or {})}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                rest_client.main(["--dry-run", *argv])
        self.assertNotEqual(cm.exception.code, 0)
        return str(cm.exception.code)

    def test_bad_identifiers(self):
        self.assert_exits(["jira", "issue", "SN-42; rm -rf"])
        self.assert_exits(["github", "issues", "just-a-name"])
        self.assert_exits(["gitlab", "issues", "a b"])

    def test_non_https_base_refused(self):
        msg = self.assert_exits(["jira", "issue", "SN-42"], {"JIRA_BASE": "http://jira.example.internal"})
        self.assertIn("HTTPS", msg)
        self.assert_exits(["jira", "issue", "SN-42"], {"JIRA_BASE": "http://localhost:8080"})
        self.assert_exits(["jira", "issue", "SN-42"], {"JIRA_BASE": "http://127.0.0.1.example.test"})

    def test_loopback_http_allowed_for_the_offline_fake(self):
        r = dry(["jira", "issue", "SN-42"], {"JIRA_BASE": "http://127.0.0.1:8089"})
        self.assertEqual(r["url"], "http://127.0.0.1:8089/rest/api/2/issue/SN-42")

    def test_ado_query_needs_saved_query_id_not_wiql_text(self):
        msg = self.assert_exits(["ado", "query", "SELECT [System.Id] FROM WorkItems"])
        self.assertIn("POST", msg)
        self.assert_exits(["ado", "workitems", "101;102"])

    def test_missing_env_does_not_leak_other_values(self):
        msg = self.assert_exits(["jira", "issue", "SN-42"], {"JIRA_TOKEN": ""})
        self.assertIn("JIRA_TOKEN", msg)
        self.assertNotIn("fake-token-value-for-tests", msg)

    def test_unknown_action(self):
        self.assert_exits(["jira", "delete", "SN-42"])


if __name__ == "__main__":
    unittest.main()
