"""Tests for the offline fake tracker server and the tracker importer. Run: python -m unittest discover -s tools/tests -q

The fake server is started in-process on 127.0.0.1 with an ephemeral port; nothing here reaches the network.
"""

import base64
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "integrations"))

import fake_server  # noqa: E402
import rest_client  # noqa: E402
import tracker_import  # noqa: E402
import tracker_report  # noqa: E402

FIXTURES = ROOT / "integrations" / "fixtures"
CRED = "unit-test-token-not-a-secret"
WRONG = "unit-test-wrong-token-value"
QUERY_ALL = "00000000-0000-4000-8000-000000000001"
QUERY_OPEN_BUGS = "00000000-0000-4000-8000-000000000002"


class Client:
    """Minimal urllib client that returns (status, headers, json) and never raises on HTTP errors."""

    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path: str, headers: dict | None = None, method: str = "GET", data: bytes | None = None):
        req = urllib.request.Request(self.base + path, headers=headers or {}, method=method, data=data)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return e.code, dict(e.headers), json.loads(body) if body else None


def bearer(token=CRED):
    return {"Authorization": f"Bearer {token}"}


def basic(token=CRED, user=""):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()}


def gitlab(token=CRED):
    return {"PRIVATE-TOKEN": token}


class FakeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = io.StringIO()
        cls.server = fake_server.FakeTrackerServer(fake_server.load_fixtures(FIXTURES), 0, CRED)
        cls.server.log_stream = cls.log
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.c = Client(cls.server.port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_binds_loopback_ephemeral(self):
        host, port = self.server.server_address[:2]
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0)
        self.assertEqual(port, self.server.port)

    # ---- happy paths ---------------------------------------------------------------------------

    def test_jira_search_and_issue(self):
        status, _, body = self.c.get("/rest/api/2/search?" + urllib.parse.urlencode({"jql": "project = SN", "maxResults": 50}), bearer())
        self.assertEqual(status, 200)
        self.assertEqual({"expand", "startAt", "maxResults", "total", "issues"}, set(body))
        self.assertEqual(body["total"], 12)
        self.assertEqual(len(body["issues"]), 12)
        keys = [i["key"] for i in body["issues"]]
        self.assertEqual(keys, [f"SN-{n}" for n in range(101, 113)])
        status, _, issue = self.c.get("/rest/api/2/issue/SN-103", basic(user="someone@example.test"))
        self.assertEqual(status, 200)
        self.assertEqual(issue["key"], "SN-103")
        self.assertEqual(issue["fields"]["status"]["name"], "In Progress")
        self.assertEqual(issue["fields"]["status"]["statusCategory"]["key"], "indeterminate")
        self.assertIn("priority", issue["fields"])
        status, _, done = self.c.get("/rest/api/2/search?" + urllib.parse.urlencode({"jql": "status = Done"}), bearer())
        self.assertEqual([i["fields"]["status"]["name"] for i in done["issues"]], ["Done"] * done["total"])

    def test_gitlab_list_headers_and_single_issue(self):
        status, headers, body = self.c.get("/api/v4/projects/123/issues?state=all&per_page=100", gitlab())
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Total"], "12")
        self.assertEqual(headers["X-Page"], "1")
        self.assertEqual(headers["X-Per-Page"], "100")
        self.assertEqual(headers["X-Next-Page"], "")
        self.assertEqual([i["iid"] for i in body], list(range(1, 13)))
        status, _, closed = self.c.get("/api/v4/projects/123/issues?state=closed", gitlab())
        self.assertTrue(closed and all(i["state"] == "closed" for i in closed))
        status, _, one = self.c.get("/api/v4/projects/123/issues/7", gitlab())
        self.assertEqual(status, 200)
        self.assertEqual((one["iid"], one["project_id"], one["state"]), (7, 123, "opened"))
        self.assertIn("workflow::proposed", self.c.get("/api/v4/projects/123/issues/10", gitlab())[2]["labels"])

    def test_ado_query_then_workitems(self):
        status, _, q = self.c.get(f"/sn-org/sensor-node/_apis/wit/wiql/{QUERY_OPEN_BUGS}?api-version=7.1", basic())
        self.assertEqual(status, 200)
        self.assertEqual(q["queryType"], "flat")
        self.assertEqual(q["queryResultType"], "workItem")
        ids = [w["id"] for w in q["workItems"]]
        self.assertEqual(ids, [103, 104, 105, 112])
        status, _, body = self.c.get(f"/sn-org/sensor-node/_apis/wit/workitems?ids={','.join(map(str, ids))}&api-version=7.1", basic())
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 4)
        self.assertEqual([w["id"] for w in body["value"]], ids)
        self.assertEqual(body["value"][0]["fields"]["System.WorkItemType"], "Issue")
        self.assertEqual(body["value"][3]["fields"]["Microsoft.VSTS.Common.Priority"], 1)
        status, _, body = self.c.get("/sn-org/sensor-node/_apis/wit/workitems?ids=101&api-version=7.1&fields=System.Title,System.State", basic())
        self.assertEqual(set(body["value"][0]["fields"]), {"System.Title", "System.State"})

    # ---- pagination ------------------------------------------------------------------------------

    def test_jira_pagination_three_pages_reassemble(self):
        keys, start, pages = [], 0, 0
        while True:
            _, _, body = self.c.get("/rest/api/2/search?" + urllib.parse.urlencode({"jql": "project = SN", "startAt": start, "maxResults": 5}), bearer())
            pages += 1
            keys += [i["key"] for i in body["issues"]]
            start = body["startAt"] + len(body["issues"])
            if start >= body["total"]:
                break
        self.assertEqual(pages, 3)
        self.assertEqual(len(keys), 12)
        self.assertEqual(len(set(keys)), 12)
        self.assertEqual([i["key"] for i in self.c.get("/rest/api/2/search?jql=project+%3D+SN", bearer())[2]["issues"]], keys)

    def test_gitlab_pagination_three_pages_reassemble(self):
        iids, page, pages = [], "1", 0
        while page:
            _, headers, body = self.c.get(f"/api/v4/projects/123/issues?state=all&per_page=5&page={page}", gitlab())
            pages += 1
            self.assertEqual(headers["X-Page"], page)
            iids += [i["iid"] for i in body]
            page = headers["X-Next-Page"]
        self.assertEqual(pages, 3)
        self.assertEqual(iids, list(range(1, 13)))
        _, headers, _ = self.c.get("/api/v4/projects/123/issues?per_page=5&page=3", gitlab())
        self.assertEqual(headers["X-Next-Page"], "")

    # ---- errors --------------------------------------------------------------------------------

    def test_missing_and_wrong_token_401(self):
        for path, hdrs in [("/rest/api/2/issue/SN-101", {}), ("/rest/api/2/issue/SN-101", bearer(WRONG)), ("/rest/api/2/issue/SN-101", basic(WRONG)),
                           ("/api/v4/projects/123/issues", {}), ("/api/v4/projects/123/issues", gitlab(WRONG)),
                           ("/api/v4/projects/123/issues", bearer()),  # Jira-style header on a GitLab path is not accepted
                           (f"/sn-org/sensor-node/_apis/wit/workitems?ids=101&api-version=7.1", {}), (f"/sn-org/sensor-node/_apis/wit/wiql/{QUERY_ALL}?api-version=7.1", bearer(WRONG))]:
            with self.subTest(path=path, headers=list(hdrs)):
                status, _, body = self.c.get(path, hdrs)
                self.assertEqual(status, 401)
                self.assertIsInstance(body, dict)
                dumped = json.dumps(body)
                self.assertNotIn(CRED, dumped)
                self.assertNotIn(WRONG, dumped)

    def test_unknown_path_and_id_404(self):
        for path, hdrs in [("/rest/api/2/issue/SN-999", bearer()), ("/api/v4/projects/123/issues/999", gitlab()), ("/api/v4/projects/999/issues", gitlab()),
                           ("/sn-org/sensor-node/_apis/wit/workitems?ids=999&api-version=7.1", basic()),
                           (f"/sn-org/sensor-node/_apis/wit/wiql/{QUERY_ALL[:-1]}f?api-version=7.1", basic()),
                           ("/rest/api/2/nope", bearer()), ("/nothing/here", {}), ("/api/v4/users", gitlab())]:
            with self.subTest(path=path):
                status, _, body = self.c.get(path, hdrs)
                self.assertEqual(status, 404)
                self.assertIsInstance(body, dict)

    def test_bad_query_params_400(self):
        cases = [("/rest/api/2/search?jql=project+%3D+SN&startAt=abc", bearer()), ("/rest/api/2/search?jql=project+%3D+SN&maxResults=-1", bearer()),
                 ("/rest/api/2/search?jql=project+%3D+SN&maxResults=100000", bearer()), ("/rest/api/2/search?jql=project+%3D+SN&bogus=1", bearer()),
                 ("/rest/api/2/search?jql=" + urllib.parse.quote("project = SN OR ;drop"), bearer()),
                 ("/api/v4/projects/123/issues?page=x", gitlab()), ("/api/v4/projects/123/issues?page=0", gitlab()), ("/api/v4/projects/123/issues?per_page=101", gitlab()),
                 ("/api/v4/projects/123/issues?state=weird", gitlab()),
                 ("/sn-org/sensor-node/_apis/wit/workitems?ids=1;2&api-version=7.1", basic()), ("/sn-org/sensor-node/_apis/wit/workitems?api-version=7.1", basic()),
                 ("/sn-org/sensor-node/_apis/wit/workitems?ids=101&api-version=9.9", basic()), ("/sn-org/sensor-node/_apis/wit/workitems?ids=101", basic()),
                 (f"/sn-org/sensor-node/_apis/wit/wiql/{QUERY_ALL}?api-version=7.1&$top=abc", basic())]
        for path, hdrs in cases:
            with self.subTest(path=path):
                status, _, body = self.c.get(path, hdrs)
                self.assertEqual(status, 400)
                self.assertIsInstance(body, dict)

    def test_write_methods_405(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in ("/rest/api/2/issue/SN-101", "/api/v4/projects/123/issues", "/sn-org/sensor-node/_apis/wit/wiql?api-version=7.1"):
                with self.subTest(method=method, path=path):
                    status, headers, body = self.c.get(path, {**bearer(), **gitlab(), "Content-Type": "application/json"}, method=method, data=b"{}")
                    self.assertEqual(status, 405)
                    self.assertEqual(headers.get("Allow"), "GET")
                    self.assertIsInstance(body, dict)
        self.assertEqual(self.c.get("/rest/api/2/issue/SN-101", bearer(), method="HEAD")[0], 405)

    def test_log_and_errors_redact_credentials(self):
        self.c.get("/rest/api/2/issue/SN-101", bearer())
        self.c.get("/rest/api/2/issue/SN-999", basic(WRONG))
        self.c.get("/api/v4/projects/123/issues/1", gitlab(WRONG))
        self.c.get("/api/v4/projects/123/issues?page=x", gitlab())
        log = self.log.getvalue()
        self.assertIn("Authorization=<redacted>", log)
        self.assertIn("PRIVATE-TOKEN=<redacted>", log)
        self.assertNotIn(CRED, log)
        self.assertNotIn(WRONG, log)
        self.assertNotIn(base64.b64encode(f":{WRONG}".encode()).decode(), log)

    # ---- rest_client against the fake -------------------------------------------------------------

    def test_rest_client_reads_all_three_apis(self):
        env = {"JIRA_BASE": self.c.base, "JIRA_TOKEN": CRED, "GITLAB_BASE": self.c.base, "GITLAB_TOKEN": CRED,
               "ADO_ORG": f"{self.c.base}/sn-org", "ADO_PROJECT": "sensor-node", "ADO_TOKEN": CRED}
        with mock.patch.dict(os.environ, env, clear=True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rest_client.main(["jira", "search", "project = SN"])
                rest_client.main(["jira", "issue", "SN-101"])
                rest_client.main(["gitlab", "issues", "123"])
                rest_client.main(["ado", "query", QUERY_ALL])
                rest_client.main(["ado", "workitems", "101,102"])
            text = out.getvalue()
            self.assertIn('"key": "SN-101"', text)
            self.assertIn('"iid": 1', text)
            self.assertIn('"queryResultType": "workItem"', text)
            self.assertIn('"count": 2', text)
            self.assertNotIn(CRED, text)
            with self.assertRaises(SystemExit) as cm:
                with contextlib.redirect_stdout(io.StringIO()):
                    rest_client.main(["jira", "issue", "SN-999"])
            self.assertIn("HTTP 404", str(cm.exception.code))
            self.assertNotIn(CRED, str(cm.exception.code))


class FakeServerCliTests(unittest.TestCase):
    def test_fixture_validation_refuses_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(FIXTURES, d, dirs_exist_ok=True)
            p = Path(d) / "jira_issues.json"
            data = json.loads(p.read_text())
            data["issues"][0]["fields"]["surprise"] = "x"
            p.write_text(json.dumps(data))
            with self.assertRaises(SystemExit) as cm:
                fake_server.load_fixtures(Path(d))
            self.assertIn("surprise", str(cm.exception.code))

    def test_bad_token_shape_refused(self):
        with self.assertRaises(SystemExit):
            fake_server.FakeTrackerServer(fake_server.load_fixtures(FIXTURES), 0, "short")

    def test_cli_rejects_bad_port(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            fake_server.main(["--port", "70000"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            fake_server.main(["--port", "-1"])

    def test_no_write_handlers_exist(self):
        for name in ("do_POST", "do_PUT", "do_PATCH", "do_DELETE"):
            self.assertIs(getattr(fake_server.Handler, name), fake_server.Handler._read_only)


class DocsInSyncTests(unittest.TestCase):
    """integrations/README.md and the two skills name only things the code has, and vice versa."""

    README = (ROOT / "integrations" / "README.md").read_text()
    SKILLS = (ROOT / ".devin/skills/connect-tools/SKILL.md").read_text() + (ROOT / ".devin/skills/track-and-report/SKILL.md").read_text()

    def test_import_modes_and_flags(self):
        for mode in tracker_import.MODES:
            self.assertIn(f"--from {mode}", self.README)
        self.assertIn("|".join(tracker_import.MODES), self.SKILLS)
        for flag in ("--from", "--in", "--out", "--merge"):
            self.assertIn(flag, self.README)
            self.assertIn(flag, self.SKILLS)
        for flag in ("--port", "--fixtures", "FAKE_TRACKER_TOKEN", fake_server.DEFAULT_TOKEN_VALUE):
            self.assertIn(flag, self.README)

    def test_error_codes_and_endpoints(self):
        src = (ROOT / "integrations" / "fake_server.py").read_text()
        for code in ("400", "401", "404", "405"):
            self.assertIn(f"`{code}`", self.README)
            self.assertIn(f"ApiError({code}" if code != "405" else "reply(405", src)
        for path in ("/rest/api/2/search", "/rest/api/2/issue/", "/api/v4/projects/", "/issues", "_apis/wit/workitems", "_apis/wit/wiql/"):
            self.assertIn(path, self.README)
        self.assertIn("Twelve synthetic", self.README)
        self.assertEqual(len(fake_server.load_fixtures(FIXTURES)["jira"]), 12)
        self.assertIn("ado query", self.README)
        self.assertIn("ado workitems", self.README)
        self.assertEqual({("ado", "query"), ("ado", "workitems")}, {k for k in rest_client.COMMANDS if k[0] == "ado"})


class TrackerImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_import(self, *argv, expect_fail=False):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_fail:
                with self.assertRaises(SystemExit) as cm:
                    tracker_import.main(list(argv))
                return str(cm.exception.code)
            self.assertEqual(tracker_import.main(list(argv)), 0)
        return out.getvalue()

    def import_fixture(self, mode: str, name: str, *extra):
        out = self.dir / f"{mode}-{len(extra)}.json"
        self.run_import("--from", mode, "--in", str(FIXTURES / name), "--out", str(out), *extra)
        return out

    def test_every_mode_imports_its_fixture_and_validates(self):
        results = {}
        for mode, name in [("jira", "jira_issues.json"), ("gitlab", "gitlab_issues.json"), ("ado", "ado_workitems.json"), ("csv", "csv_export.csv")]:
            with self.subTest(mode=mode):
                out = self.import_fixture(mode, name)
                items = tracker_report.load(out)
                self.assertEqual(len(items), 12)
                self.assertTrue(all(i["source"].startswith(mode + ":") for i in items))
                results[mode] = [{k: v for k, v in i.items() if k not in ("source", "owner")} for i in items]
        self.assertEqual(set(tracker_import.MODES), set(results))
        # the four fixtures describe the same twelve items, so every reader must normalise to the same tracker
        self.assertEqual(results["jira"], results["gitlab"])
        self.assertEqual(results["jira"], results["ado"])
        self.assertEqual(results["jira"], results["csv"])
        statuses = {i["status"] for i in results["jira"]}
        self.assertEqual(statuses, set(tracker_import.STATUSES))
        self.assertEqual({i["severity"] for i in results["jira"]}, set(tracker_import.SEVERITIES))
        self.assertEqual({i["type"] for i in results["jira"]}, set(tracker_import.TYPES))
        self.assertEqual(results["jira"][0]["id"], "SN-BUG-001")
        self.assertEqual([i["id"] for i in results["jira"]][-1], "SN-CAP-006")

    def test_csv_owner_column_is_kept(self):
        items = tracker_report.load(self.import_fixture("csv", "csv_export.csv"))
        self.assertEqual({i["owner"] for i in items}, {"firmware", "systems"})

    def test_mapping_tables_only_produce_schema_values(self):
        for table, allowed in [(tracker_import.JIRA_TYPE, tracker_import.TYPES), (tracker_import.GITLAB_TYPE, tracker_import.TYPES), (tracker_import.ADO_TYPE, tracker_import.TYPES),
                               (tracker_import.JIRA_SEVERITY, tracker_import.SEVERITIES), (tracker_import.ADO_SEVERITY, tracker_import.SEVERITIES),
                               (tracker_import.JIRA_STATUS, tracker_import.STATUSES), (tracker_import.ADO_STATUS, tracker_import.STATUSES),
                               (tracker_import.GITLAB_WORKFLOW, tracker_import.STATUSES), (tracker_import.GITLAB_STATE, tracker_import.STATUSES)]:
            self.assertTrue(set(table.values()) <= set(allowed), table)

    def test_idempotent_reimport_and_merge_updates_not_duplicates(self):
        first = self.import_fixture("jira", "jira_issues.json")
        second = self.dir / "second.json"
        out = self.run_import("--from", "jira", "--in", str(FIXTURES / "jira_issues.json"), "--out", str(second), "--merge", str(first))
        self.assertIn("12 updated, 0 added", out)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        # a changed export updates the matching item in place and keeps its tracker id and hand-set owner
        data = json.loads((FIXTURES / "jira_issues.json").read_text())
        data["issues"][2]["fields"]["status"] = {"name": "Done", "statusCategory": {"key": "done", "name": "Done"}}
        data["issues"][2]["fields"]["resolutiondate"] = "2026-04-01T10:00:00.000+0000"
        changed = self.dir / "changed.json"
        changed.write_text(json.dumps(data))
        base = json.loads(first.read_text())
        base["items"][2]["owner"] = "firmware"
        first.write_text(json.dumps(base))
        third = self.dir / "third.json"
        self.run_import("--from", "jira", "--in", str(changed), "--out", str(third), "--merge", str(first))
        items = tracker_report.load(third)
        self.assertEqual(len(items), 12)
        sn103 = [i for i in items if i["source"] == "jira:SN-103"]
        self.assertEqual(len(sn103), 1)
        self.assertEqual((sn103[0]["id"], sn103[0]["status"], sn103[0]["closed"], sn103[0]["owner"]), ("SN-BUG-003", "closed", "2026-04-01", "firmware"))

    def test_merge_into_example_tracker_appends_after_existing_ids(self):
        out = self.dir / "merged.json"
        self.run_import("--from", "ado", "--in", str(FIXTURES / "ado_workitems.json"), "--out", str(out), "--merge", str(tracker_report.DEFAULT))
        items = tracker_report.load(out)
        self.assertEqual(len(items), 10 + 12)
        self.assertEqual([i["id"] for i in items if i["id"].startswith("SN-BUG")][-1], "SN-BUG-011")
        self.assertEqual(json.loads(out.read_text())["_about"], json.loads(tracker_report.DEFAULT.read_text())["_about"])

    def test_unknown_status_and_priority_rejected_with_allowed_set(self):
        data = json.loads((FIXTURES / "jira_issues.json").read_text())
        data["issues"][0]["fields"]["status"]["name"] = "Parked"
        bad = self.dir / "bad.json"
        bad.write_text(json.dumps(data))
        msg = self.run_import("--from", "jira", "--in", str(bad), "--out", str(self.dir / "x.json"), expect_fail=True)
        self.assertIn("Parked", msg)
        self.assertIn("SN-101", msg)
        for allowed in tracker_import.JIRA_STATUS:
            self.assertIn(allowed, msg)
        self.assertFalse((self.dir / "x.json").exists())
        data = json.loads((FIXTURES / "ado_workitems.json").read_text())
        data["value"][0]["fields"]["Microsoft.VSTS.Common.Priority"] = 9
        bad.write_text(json.dumps(data))
        msg = self.run_import("--from", "ado", "--in", str(bad), "--out", str(self.dir / "x.json"), expect_fail=True)
        self.assertIn("Priority", msg)
        self.assertIn("'1', '2', '3', '4'", msg)
        rows = (FIXTURES / "csv_export.csv").read_text().splitlines()
        rows[1] = rows[1].replace(",closed,", ",resolved,")
        (self.dir / "bad.csv").write_text("\n".join(rows) + "\n")
        msg = self.run_import("--from", "csv", "--in", str(self.dir / "bad.csv"), "--out", str(self.dir / "x.json"), expect_fail=True)
        self.assertIn("resolved", msg)
        self.assertIn("wont_fix", msg)

    def test_unknown_fields_dropped_and_bad_shapes_refused(self):
        data = json.loads((FIXTURES / "gitlab_issues.json").read_text())
        data[0]["assignee"] = {"name": "not a field we keep"}
        data[0]["web_url"] = "http://127.0.0.1/x"
        src = self.dir / "gl.json"
        src.write_text(json.dumps(data))
        out = self.dir / "gl-out.json"
        self.run_import("--from", "gitlab", "--in", str(src), "--out", str(out))
        item = tracker_report.load(out)[0]
        self.assertEqual(set(item), set(tracker_import.FIELDS) | {"source"})
        self.assertNotIn("not a field we keep", out.read_text())
        for payload in ('{"issues": "nope"}', "[1, 2]", "{not json", '[{"iid": "7", "project_id": 1}]'):
            src.write_text(payload)
            msg = self.run_import("--from", "gitlab", "--in", str(src), "--out", str(out), expect_fail=True)
            self.assertTrue(msg.startswith("tracker_import:"), msg)
        (self.dir / "h.csv").write_text("id,title\nX,Y\n")
        msg = self.run_import("--from", "csv", "--in", str(self.dir / "h.csv"), "--out", str(out), expect_fail=True)
        self.assertIn("header", msg)

    def test_duplicate_external_id_in_one_export_refused(self):
        data = json.loads((FIXTURES / "jira_issues.json").read_text())
        data["issues"].append(data["issues"][0])
        src = self.dir / "dup.json"
        src.write_text(json.dumps(data))
        msg = self.run_import("--from", "jira", "--in", str(src), "--out", str(self.dir / "x.json"), expect_fail=True)
        self.assertIn("duplicate", msg)


if __name__ == "__main__":
    unittest.main()
