import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from integrations import fake_server
from tools import coverage_gate, plan_to_tracker, sonar_gate

COVERAGE_FIXTURES = ROOT / "tools" / "tests" / "fixtures" / "coverage"
SONAR_FIXTURES = ROOT / "integrations" / "fixtures"
FAKE_AUTH = "test-token-value"


class CoverageGateTests(unittest.TestCase):
    def test_lcov_threshold_boundary_and_failure(self):
        changed = coverage_gate.parse_diff((COVERAGE_FIXTURES / "sample.diff").read_text())
        report = coverage_gate.read_lcov(COVERAGE_FIXTURES / "lcov.info", None)
        self.assertTrue(coverage_gate.summarize(changed, report, 79.99)["pass"])
        self.assertTrue(coverage_gate.summarize(changed, report, 80.0)["pass"])
        self.assertFalse(coverage_gate.summarize(changed, report, 80.01)["pass"])

    def test_cobertura_and_path_prefix(self):
        diff = "diff --git a/src/sample.ts b/src/sample.ts\n--- a/src/sample.ts\n+++ b/src/sample.ts\n@@ -1 +1 @@\n-old\n+new\n"
        report = coverage_gate.read_cobertura(COVERAGE_FIXTURES / "cobertura.xml", None)
        self.assertEqual(coverage_gate.summarize(coverage_gate.parse_diff(diff), report, 80)["covered"], 1)
        absolute = COVERAGE_FIXTURES / "prefix.info"
        absolute.write_text("SF:/workspace/app/src/sample.ts\nDA:1,1\nend_of_record\n", encoding="utf-8")
        try:
            mapped = coverage_gate.read_lcov(absolute, "/workspace/app")
            self.assertIn("src/sample.ts", mapped)
        finally:
            absolute.unlink()

    def test_no_changed_lines_passes_with_note(self):
        summary = coverage_gate.summarize({}, {}, 80)
        self.assertTrue(summary["pass"])
        self.assertEqual(summary["note"], "No measurable changed lines.")

    def test_rename_deleted_file_and_crlf(self):
        diff = (
            "diff --git a/old.ts b/new.ts\r\n"
            "similarity index 90%\r\nrename from old.ts\r\nrename to new.ts\r\n"
            "--- a/old.ts\r\n+++ b/new.ts\r\n@@ -1 +1,2 @@\r\n-old\r\n+new\r\n+next\r\n"
            "diff --git a/gone.ts b/gone.ts\r\ndeleted file mode 100644\r\n"
            "--- a/gone.ts\r\n+++ /dev/null\r\n@@ -1 +0,0 @@\r\n-removed\r\n"
        )
        changes = coverage_gate.parse_diff(diff)
        self.assertEqual(changes, {"new.ts": {1, 2}})
        report = {"new.ts": {1: 1, 2: 0}, "gone.ts": {1: 1}}
        summary = coverage_gate.summarize(changes, report, 50)
        self.assertEqual(summary["files"][0]["uncovered_ranges"], "2")


class SonarGateTests(unittest.TestCase):
    def test_gate_statuses_and_new_issue_shapes(self):
        issues = {"issues": [
            {"severity": "CRITICAL", "type": "VULNERABILITY", "component": "p:file.ts", "line": 8, "message": "legacy"},
            {"impacts": [{"softwareQuality": "SECURITY", "severity": "HIGH"}], "component": "p:next.ts", "line": 9},
        ]}
        for status in ("OK", "ERROR", "WARN", "NONE"):
            summary = sonar_gate.summarize({"projectStatus": {"status": status, "conditions": []}}, issues, "p", None, None)
            self.assertEqual(summary["gate_status"], status)
        self.assertEqual(summary["note"].startswith("Quality gate status is NONE"), True)
        result = sonar_gate.summarize({"projectStatus": {"status": "OK", "conditions": []}}, issues, "p", None, None)
        self.assertEqual(result["issues"][1]["severity"], "HIGH")
        self.assertEqual(result["issues"][1]["type"], "SECURITY")

    def test_gate_exit_codes(self):
        cases = {"OK": 0, "ERROR": 3, "WARN": 0, "NONE": 2}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            status_path = Path(directory) / "status.json"
            issues_path = Path(directory) / "issues.json"
            issues_path.write_text(json.dumps({"issues": []}))
            for status, expected in cases.items():
                status_path.write_text(json.dumps({"projectStatus": {"status": status, "conditions": []}}))
                self.assertEqual(
                    sonar_gate.main(["--status-file", str(status_path), "--issues-file", str(issues_path)]),
                    expected,
                )
            status_path.write_text(json.dumps({"projectStatus": {"status": "WARN", "conditions": []}}))
            self.assertEqual(
                sonar_gate.main(["--status-file", str(status_path), "--issues-file", str(issues_path), "--fail-on-warn"]),
                4,
            )

    def test_api_pagination_and_fake_server_auth(self):
        token = FAKE_AUTH
        fixtures = fake_server.load_fixtures(SONAR_FIXTURES)
        server = fake_server.FakeTrackerServer(fixtures, 0, token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.port}"
            with mock.patch.object(sonar_gate, "PAGE_SIZE", 1):
                status, issues = sonar_gate.get_live(base, token, "synthetic-project", "main", None)
            self.assertEqual(status["projectStatus"]["status"], "ERROR")
            self.assertEqual(len(issues["issues"]), 2)
            self.assertEqual(issues["issues"][0]["severity"], "CRITICAL")
            system_status = urlopen(Request(base + "/api/system/status", headers={"Authorization": f"Bearer {token}"}), timeout=3)
            self.assertEqual(system_status.status, 200)
            system_status.close()
            for path in ("/api/system/status", "/api/qualitygates/project_status?projectKey=synthetic-project",
                         "/api/issues/search?" + urlencode({"componentKeys": "synthetic-project", "inNewCodePeriod": "true"})):
                for headers in ({}, {"Authorization": "Bearer wrong-token"}):
                    request = Request(base + path, headers=headers)
                    with self.assertRaises(Exception) as failure:
                        urlopen(request, timeout=3)
                    self.assertEqual(getattr(failure.exception, "code", None), 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class PlanToTrackerTests(unittest.TestCase):
    def test_parse_and_deterministic_payload(self):
        first = plan_to_tracker.make_payloads(plan_to_tracker.DEFAULT_SPEC, "SN", "Task")
        self.assertEqual(first, plan_to_tracker.make_payloads(plan_to_tracker.DEFAULT_SPEC, "SN", "Task"))
        self.assertEqual(len(first["issues"]), 15)
        fields = first["issues"][0]["payload"]["fields"]
        self.assertEqual(fields["labels"], ["spec-001"])
        self.assertIn("feature/<KEY-placeholder>-diagnostics-packet", fields["description"])
        self.assertIn("set by the owner in Jira", fields["description"])
        self.assertNotIn("assignee", fields)

    def test_apply_requires_flag_and_environment(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {}, clear=True):
            result = plan_to_tracker.main(["--apply", "--out", str(Path(directory) / "payload.json")])
            self.assertEqual(result, 2)
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"JIRA_URL": "https://jira.example.invalid", "JIRA_TOKEN": FAKE_AUTH}, clear=True
        ), contextlib.redirect_stdout(io.StringIO()):
            output = Path(directory) / "payload.json"
            self.assertEqual(plan_to_tracker.main(["--out", str(output)]), 0)
            self.assertIsNone(json.loads(output.read_text(encoding="utf-8"))["issues"][0]["created_key"])

    def test_apply_posts_one_at_a_time_to_local_stub(self):
        requests = []

        class Stub(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, data, self.headers.get("Authorization")))
                body = json.dumps({"key": f"SN-{len(requests)}"}).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"JIRA_URL": f"http://127.0.0.1:{server.server_port}", "JIRA_TOKEN": FAKE_AUTH}, clear=True
            ), contextlib.redirect_stdout(io.StringIO()):
                output = Path(directory) / "payload.json"
                self.assertEqual(plan_to_tracker.main(["--apply", "--yes", "--out", str(output)]), 0)
                saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(requests), 15)
            self.assertTrue(all(path == "/rest/api/2/issue" for path, _, _ in requests))
            self.assertTrue(all(auth == f"Bearer {FAKE_AUTH}" for _, _, auth in requests))
            self.assertEqual(saved["issues"][-1]["created_key"], "SN-15")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class MainBranchHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hook_path = ROOT / "templates" / "team-repo" / "hooks" / "block_main.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("block_main", hook_path)
        cls.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.hook)

    def check(self, command, branch, blocked):
        with mock.patch.object(self.hook.subprocess, "run") as run:
            run.return_value.stdout = branch + "\n"
            run.return_value.returncode = 0
            event = {"tool_name": "exec", "tool_input": {"command": command}}
            result = self.hook.evaluate(event)
        self.assertEqual(result, blocked, command)

    def test_main_commit_and_push_variants_block(self):
        self.check("git commit -m update", "main", True)
        self.check("git commit -m update", "master", True)
        self.check("git push origin", "main", True)
        self.check("git push --force origin HEAD:main", "feature/work", True)
        self.check("git push --force origin HEAD:refs/heads/main", "feature/work", True)
        self.check("git push --all origin", "feature/work", True)
        self.check("git push origin feature/work:refs/heads/master", "feature/work", True)
        self.check("git push origin main", "feature/work", True)

    def test_feature_branch_operations_pass(self):
        self.check("git commit -m update", "feature/work", False)
        self.check("git push origin feature/work", "feature/work", False)


if __name__ == "__main__":
    unittest.main()
