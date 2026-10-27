import contextlib
import hashlib
import io
import json
import os
import subprocess
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
        for threshold in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                coverage_gate.summarize(changed, report, threshold)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                coverage_gate.main(["--lcov", str(COVERAGE_FIXTURES / "lcov.info"),
                                    "--diff-file", str(COVERAGE_FIXTURES / "sample.diff"),
                                    "--threshold", str(threshold)])

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

    def test_hunk_counts_added_plus_prefix_lines_and_quoted_paths(self):
        diff = (COVERAGE_FIXTURES / "space-path.diff").read_text(encoding="utf-8")
        self.assertEqual(coverage_gate.parse_diff(diff), {"src/My Component.ts": {1}})
        plus_line = (
            "diff --git a/counter.ts b/counter.ts\n--- a/counter.ts\n+++ b/counter.ts\n"
            "@@ -1,0 +1,2 @@\n++counter;\n+next();\n"
        )
        self.assertEqual(coverage_gate.parse_diff(plus_line), {"counter.ts": {1, 2}})
        renamed = (
            'diff --git a/old.ts b/new.ts\nrename to "src/My\\040Component.ts"\n'
            '--- a/old.ts\n+++ "b/src/My\\040Component.ts"\n@@ -1 +1 @@\n-old\n+new\n'
        )
        self.assertEqual(coverage_gate.decode_git_path('"b/src/My\\040Component.ts"'), "b/src/My Component.ts")
        self.assertEqual(coverage_gate.parse_diff(renamed), {"src/My Component.ts": {1}})

    def test_base_diff_includes_tracked_worktree_and_untracked_files(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as report_directory:
            repo = Path(directory)
            (repo / "src").mkdir()
            tracked = repo / "src" / "app.ts"
            tracked.write_text("const old = 1;\nconst keep = 2;\n", encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "GIT_AUTHOR_NAME": "Synthetic Test",
                "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
                "GIT_COMMITTER_NAME": "Synthetic Test",
                "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
            })

            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, env=environment, check=True,
                                      capture_output=True, text=True)

            git("init", "-b", "main")
            git("add", "src/app.ts")
            git("commit", "-m", "fixture base")
            tracked.write_text("const staged = 1;\nconst keep = 2;\n", encoding="utf-8")
            git("add", "src/app.ts")
            tracked.write_text("const staged = 1;\nconst unstaged = 2;\n", encoding="utf-8")
            new_file = repo / "src" / "new file.ts"
            new_file.write_text("const first = 1;\nconst second = 2;\n", encoding="utf-8")
            lcov = Path(report_directory) / "lcov.info"
            lcov.write_text(
                "SF:src/app.ts\nDA:1,1\nDA:2,1\nend_of_record\n"
                "SF:src/new file.ts\nDA:1,1\nDA:2,1\nend_of_record\n",
                encoding="utf-8",
            )
            args = type("Args", (), {
                "diff_file": None,
                "base": "main",
                "repo": directory,
                "lcov": str(lcov),
                "cobertura": None,
                "path_prefix": None,
            })()
            changed, _ = coverage_gate.load_inputs(args)
            self.assertEqual(changed, {"src/app.ts": {1, 2}, "src/new file.ts": {1, 2}})


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
        warning = {"projectStatus": {"status": "WARN", "conditions": []}}
        self.assertTrue(sonar_gate.summarize(warning, {"issues": []}, "p", None, None)["pass"])
        self.assertFalse(sonar_gate.summarize(
            warning, {"issues": []}, "p", None, None, fail_on_warn=True
        )["pass"])

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
            warning_output = io.StringIO()
            with contextlib.redirect_stdout(warning_output):
                warning_exit = sonar_gate.main([
                    "--status-file", str(status_path), "--issues-file", str(issues_path),
                    "--fail-on-warn", "--json",
                ])
            self.assertEqual(warning_exit, 4)
            self.assertFalse(json.loads(warning_output.getvalue())["pass"])

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
                self.assertEqual(saved["jira_url"], plan_to_tracker.normalize_jira_url(
                    os.environ["JIRA_URL"]
                ))
                posted = saved["issues"][0]
                self.assertEqual(posted["posted_payload_sha256"], posted["posted_sha256"])
                self.assertEqual(
                    posted["posted_payload_sha256"],
                    plan_to_tracker.hashlib.sha256(
                        plan_to_tracker.canonical_payload(posted)
                    ).hexdigest(),
                )
                self.assertEqual(plan_to_tracker.main(["--apply", "--yes", "--out", str(output)]), 0)
            self.assertEqual(len(requests), 15)
            self.assertTrue(all(path == "/rest/api/2/issue" for path, _, _ in requests))
            self.assertTrue(all(auth == f"Bearer {FAKE_AUTH}" for _, _, auth in requests))
            self.assertEqual(saved["issues"][-1]["created_key"], "SN-15")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_jira_state_is_instance_bound_and_dry_run_preserves_url(self):
        requests = []

        class NoPostStub(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                self.send_response(201)
                self.end_headers()

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), NoPostStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "payload.json"
                existing = plan_to_tracker.make_payloads(plan_to_tracker.DEFAULT_SPEC, "SN", "Task")
                existing["jira_url"] = "https://old.example.invalid/context"
                plan_to_tracker.persist(existing, output)
                current_url = f"http://127.0.0.1:{server.server_port}/JIRA/"
                with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(plan_to_tracker.main(["--out", str(output)]), 0)
                dry_run_state = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(dry_run_state["jira_url"], existing["jira_url"])

                errors = io.StringIO()
                with mock.patch.dict(
                    os.environ, {"JIRA_URL": current_url, "JIRA_TOKEN": FAKE_AUTH}, clear=True
                ), contextlib.redirect_stderr(errors):
                    self.assertEqual(plan_to_tracker.main(["--apply", "--yes", "--out", str(output)]), 2)
                self.assertIn(
                    "state file belongs to https://old.example.invalid/context; use a new --out or reconcile",
                    errors.getvalue(),
                )
                self.assertEqual(requests, [])
                self.assertEqual(
                    plan_to_tracker.normalize_jira_url("HTTPS://JIRA.Example.invalid/context/"),
                    "https://jira.example.invalid/context",
                )
                self.assertEqual(
                    plan_to_tracker.normalize_jira_url("https://jira.example.invalid:443/context"),
                    plan_to_tracker.normalize_jira_url("https://jira.example.invalid/context"),
                )
                self.assertEqual(
                    plan_to_tracker.normalize_jira_url("http://jira.example.invalid:80/context/"),
                    plan_to_tracker.normalize_jira_url("http://jira.example.invalid/context"),
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_changed_posted_task_is_marked_stale_without_repost(self):
        requests = []

        class CaptureStub(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.rfile.read(int(self.headers["Content-Length"])))
                body = json.dumps({"key": "SN-42"}).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                spec_dir = Path(directory) / "001-request-form"
                spec_dir.mkdir()
                tasks = spec_dir / "tasks.md"
                tasks.write_text("- [ ] T1.1 Create the first request `python -m unittest`\n", encoding="utf-8")
                output = Path(directory) / "payload.json"
                csv_path = Path(directory) / "payload.csv"
                base = f"http://127.0.0.1:{server.server_port}/jira/"
                args = [
                    str(tasks), "--out", str(output), "--csv", str(csv_path), "--apply", "--yes"
                ]
                first_stdout = io.StringIO()
                with mock.patch.dict(
                    os.environ, {"JIRA_URL": base, "JIRA_TOKEN": FAKE_AUTH}, clear=True
                ), contextlib.redirect_stdout(first_stdout):
                    self.assertEqual(plan_to_tracker.main(args), 0)
                first_state = json.loads(output.read_text(encoding="utf-8"))
                original_hash = first_state["issues"][0]["posted_payload_sha256"]
                self.assertEqual(hashlib.sha256(requests[0]).hexdigest(), original_hash)

                tasks.write_text("- [ ] T1.1 Create the revised request `python -m unittest`\n", encoding="utf-8")
                second_stdout = io.StringIO()
                with mock.patch.dict(
                    os.environ, {"JIRA_URL": base, "JIRA_TOKEN": FAKE_AUTH}, clear=True
                ), contextlib.redirect_stdout(second_stdout):
                    self.assertEqual(plan_to_tracker.main(args), 0)
                state = json.loads(output.read_text(encoding="utf-8"))
                note = "T1.1 (SN-42) changed since posting; update the issue in Jira by hand"
                self.assertEqual(len(requests), 1)
                self.assertEqual(state["issues"][0]["created_key"], "SN-42")
                self.assertTrue(state["issues"][0]["stale"])
                self.assertEqual(state["issues"][0]["posted_payload_sha256"], original_hash)
                self.assertEqual(state["issues"][0]["posted_sha256"], original_hash)
                self.assertIn(note, second_stdout.getvalue())
                self.assertIn(note, output.with_suffix(".md").read_text(encoding="utf-8"))
                self.assertIn(note, csv_path.read_text(encoding="utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_redirect_is_refused_without_following_location(self):
        requests = []

        class RedirectStub(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                if self.path.endswith("/issue"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirect-target")
                    self.end_headers()

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"JIRA_URL": f"http://127.0.0.1:{server.server_port}", "JIRA_TOKEN": FAKE_AUTH}, clear=True
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
                output = Path(directory) / "payload.json"
                self.assertEqual(plan_to_tracker.main(["--apply", "--yes", "--out", str(output)]), 2)
                self.assertIn("HTTP 302", errors.getvalue())
                saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(requests, ["/rest/api/2/issue"])
            self.assertTrue(saved["issues"][0]["posting"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_partial_failure_rerun_requires_reconciliation_and_does_not_duplicate(self):
        requests = []

        class PartialStub(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                if len(requests) == 2:
                    self.send_response(500)
                    self.end_headers()
                    return
                body = json.dumps({"key": f"SN-{len(requests)}"}).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), PartialStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {"JIRA_URL": f"http://127.0.0.1:{server.server_port}", "JIRA_TOKEN": FAKE_AUTH}, clear=True
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
                output = Path(directory) / "payload.json"
                argv = ["--apply", "--yes", "--out", str(output)]
                self.assertEqual(plan_to_tracker.main(argv), 2)
                saved = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(plan_to_tracker.main(argv), 2)
                self.assertIn("reconcile in Jira", errors.getvalue())
            self.assertEqual(len(requests), 2)
            self.assertEqual(saved["issues"][0]["created_key"], "SN-1")
            self.assertTrue(saved["issues"][1]["posting"])
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
