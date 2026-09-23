#!/usr/bin/env python3
"""Offline fake of the read-only Jira, GitLab, and Azure DevOps endpoints that rest_client.py and curl use.

    python integrations/fake_server.py                         # 127.0.0.1, ephemeral port, prints the port
    python integrations/fake_server.py --port 8089 --fixtures integrations/fixtures
    FAKE_TRACKER_TOKEN=my-practice-token python integrations/fake_server.py

The only accepted credential is FAKE_TRACKER_TOKEN (default fake-token-for-local-tests):
  Jira and Azure DevOps: Authorization: Bearer <token>  or  Authorization: Basic base64(anything:<token>)
  GitLab:                PRIVATE-TOKEN: <token>

Endpoints (GET only; every other method is 405):
  GET /rest/api/2/myself                                   Jira Data Center: the user behind the token (CLI login check)
  GET /rest/api/2/serverInfo                               Jira Data Center: version and deploymentType ("Server")
  GET /rest/api/2/search?jql=&startAt=&maxResults=        Jira search: startAt, maxResults, total, issues[]
  GET /rest/api/2/issue/{key}                              Jira single issue
  GET /rest/api/2/project                                  Jira projects derived from the fixture keys (CLI bootstrap)
  GET /rest/api/2/field                                    Jira field list = the fixture field names (CLI bootstrap)
  GET /rest/api/2/issue/createmeta/{key}/issuetypes        Jira issue types present in the fixture (CLI bootstrap)
  GET /rest/agile/1.0/board?projectKeyOrId=                Jira Agile boards: always an empty, complete page (CLI bootstrap)
  GET /api/v4/projects/{id}/issues?page=&per_page=&state=  GitLab list: X-Total, X-Page, X-Per-Page, X-Next-Page
  GET /api/v4/projects/{id}/issues/{iid}                   GitLab single issue
  GET /{org}/{project}/_apis/wit/workitems?ids=1,2&api-version=7.1   Azure DevOps list: count, value[]
  GET /{org}/{project}/_apis/wit/wiql/{queryId}?api-version=7.1      Azure DevOps saved query: workItems[]

Errors are JSON: 401 missing/wrong credential, 404 unknown path or id, 400 bad query parameter, 405 non-GET,
500 for an unexpected failure (generic body; the detail goes to the server log only).
Credential header values are never echoed; the request log prints them as <redacted>.

The JQL the fake understands: project, status, statusCategory, issuetype (alias type) with =, !=, IN, NOT IN,
joined by AND; an optional trailing ORDER BY is ignored. That is what jira-cli v1.7.0 sends for `issue list`.
`jira init --installation local` made six GETs against this fake, in this order: myself, serverInfo, project,
agile board, issue/createmeta/{key}/issuetypes, field. Nothing else is served; anything else is 404.

Azure DevOps offers WIQL as POST (ad-hoc query text) and as GET by saved query id. This fake serves only the
GET form, so the server has no non-GET handler and a client can be checked with "GET only" alone.

Response field names follow the public documentation (checked 2026-09):
  Jira myself    https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-myself/
  Jira serverInfo https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-serverinfo/
  Jira search    https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issue-search/#api-rest-api-2-search-get
  Jira issue     https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issues/#api-rest-api-2-issue-issueidorkey-get
  Jira project/field/createmeta/agile board: shapes reduced to what jira-cli reads; see integrations/jira-on-prem.md
  GitLab issues  https://docs.gitlab.com/api/issues/
  GitLab paging  https://docs.gitlab.com/api/rest/#pagination
  ADO list       https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/list?view=azure-devops-rest-7.1
  ADO get        https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/get-work-item?view=azure-devops-rest-7.1
  ADO wiql by id https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/wiql/query-by-id?view=azure-devops-rest-7.1
  ADO fields     https://learn.microsoft.com/en-us/azure/devops/boards/queries/query-by-workflow-changes?view=azure-devops

Standard library only. Binds 127.0.0.1 only. Fixture shapes are validated on load; unexpected keys are refused.
"""

import argparse
import base64
import binascii
import hmac
import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURES = HERE / "fixtures"
DEFAULT_TOKEN_VALUE = "fake-token-for-local-tests"
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9._%-]{1,64}$")
INT_RE = re.compile(r"^[0-9]{1,6}$")
IDS_RE = re.compile(r"^[0-9]{1,10}(,[0-9]{1,10}){0,199}$")  # Azure DevOps work item ids are int32
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
JIRA_KEY_RE = re.compile(r"^[A-Z]{2,6}-[0-9]{1,6}$")
JQL_RE = re.compile(r"^[A-Za-z0-9 =!_'\"(),-]{1,200}$")
JQL_VALUE = r"(?:\"[^\"]{1,40}\"|'[^']{1,40}'|[A-Za-z0-9_-]{1,40})"
JQL_CLAUSE_RE = re.compile(rf"^(project|status|statusCategory|issuetype|type)\s*(=|!=|(?i:IN)|(?i:NOT\s+IN))\s*({JQL_VALUE}|\(\s*{JQL_VALUE}(?:\s*,\s*{JQL_VALUE}){{0,9}}\s*\))$")
MAX_PATH = 2048
MAX_PAGE_SIZE = 100
MAX_PAGES = 1000
MAX_START_AT = 10000
REDACTED_HEADERS = ("Authorization", "PRIVATE-TOKEN")
ASOF = "2026-03-15T00:00:00Z"

JIRA_FIELDS = {"summary", "description", "status", "priority", "issuetype", "components", "labels", "created", "updated", "resolutiondate"}
JIRA_REQUIRED = {"summary", "status", "priority", "issuetype", "created"}
GITLAB_FIELDS = {"id", "iid", "project_id", "title", "description", "state", "labels", "issue_type", "created_at", "updated_at", "closed_at"}
GITLAB_REQUIRED = {"id", "iid", "project_id", "title", "state", "labels", "created_at"}
ADO_FIELDS = {"System.Id", "System.TeamProject", "System.AreaPath", "System.WorkItemType", "System.State", "System.Title",
              "System.Description", "System.Tags", "System.CreatedDate", "System.ChangedDate", "Microsoft.VSTS.Common.Priority",
              "Microsoft.VSTS.Common.ClosedDate"}
ADO_REQUIRED = {"System.Id", "System.TeamProject", "System.WorkItemType", "System.State", "System.Title", "System.CreatedDate"}
ADO_COLUMNS = ("System.Id", "System.WorkItemType", "System.Title", "System.State")
GITLAB_STATES = ("opened", "closed", "all")
# Synthetic identity returned by GET /rest/api/2/myself; no fixture needed. Field names follow Jira Data Center.
JIRA_ME = {"key": "practice-user", "name": "practice-user", "emailAddress": "practice-user@example.invalid",
           "displayName": "Practice User", "active": True, "timeZone": "UTC", "locale": "en_US"}
JIRA_SERVER_INFO = {"version": "10.3.0", "versionNumbers": [10, 3, 0], "deploymentType": "Server", "buildNumber": 1030000,
                    "buildDate": "2026-01-01T00:00:00.000+0000", "scmInfo": "0000000000000000000000000000000000000000",
                    "serverTitle": "Fake Jira Data Center"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---- fixtures ----------------------------------------------------------------------------------

def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"fixture error: {msg}")


def _check_shape(name: str, item: dict, allowed: set, required: set) -> None:
    _expect(isinstance(item, dict), f"{name}: each entry must be an object")
    extra = set(item) - allowed
    _expect(not extra, f"{name}: unexpected keys {sorted(extra)}")
    missing = required - set(item)
    _expect(not missing, f"{name}: missing keys {sorted(missing)}")


def _named(name: str, fields: dict, key: str) -> dict:
    v = fields.get(key)
    _expect(isinstance(v, dict) and isinstance(v.get("name"), str), f"{name}: {key} must be an object with a name")
    return v


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SystemExit(f"fixture error: cannot read {path.name}: {e}")


def load_fixtures(folder: Path) -> dict:
    jira = _read_json(folder / "jira_issues.json")
    _expect(isinstance(jira, dict) and set(jira) == {"issues"} and isinstance(jira["issues"], list), 'jira_issues.json must be {"issues": [...]}')
    for it in jira["issues"]:
        _check_shape("jira issue", it, {"id", "key", "fields"}, {"id", "key", "fields"})
        _expect(isinstance(it["id"], str) and INT_RE.match(it["id"]) is not None, f"jira {it.get('key')}: id must be a numeric string")
        _expect(isinstance(it["key"], str) and JIRA_KEY_RE.match(it["key"]) is not None, f"jira {it.get('key')!r}: bad key")
        _check_shape(f"jira {it['key']} fields", it["fields"], JIRA_FIELDS, JIRA_REQUIRED)
        _named(f"jira {it['key']}", _named(f"jira {it['key']}", it["fields"], "status"), "statusCategory")
        _named(f"jira {it['key']}", it["fields"], "issuetype")
        _named(f"jira {it['key']}", it["fields"], "priority")
        comps = it["fields"].get("components", [])
        _expect(isinstance(comps, list) and all(isinstance(c, dict) and isinstance(c.get("name"), str) for c in comps),
                f"jira {it['key']}: components must be a list of objects with a name")
    _expect(len({i["key"] for i in jira["issues"]}) == len(jira["issues"]), "jira: duplicate keys")

    gitlab = _read_json(folder / "gitlab_issues.json")
    _expect(isinstance(gitlab, list), "gitlab_issues.json must be a list of issues")
    for it in gitlab:
        _check_shape("gitlab issue", it, GITLAB_FIELDS, GITLAB_REQUIRED)
        _expect(isinstance(it["iid"], int) and isinstance(it["project_id"], int), f"gitlab {it.get('iid')}: iid and project_id must be integers")
        _expect(it["state"] in GITLAB_STATES[:2], f"gitlab {it['iid']}: state must be opened or closed")
        _expect(isinstance(it["labels"], list), f"gitlab {it['iid']}: labels must be a list")
    _expect(len({i["project_id"] for i in gitlab}) == 1, "gitlab: need at least one issue, all sharing one project_id")
    _expect(len({i["iid"] for i in gitlab}) == len(gitlab), "gitlab: duplicate iids")

    ado = _read_json(folder / "ado_workitems.json")
    _expect(isinstance(ado, dict) and set(ado) == {"count", "value", "queries"}, 'ado_workitems.json must be {"count", "value", "queries"}')
    _expect(isinstance(ado["value"], list) and ado["count"] == len(ado["value"]), "ado: count must equal len(value)")
    for it in ado["value"]:
        _check_shape("ado work item", it, {"id", "rev", "fields"}, {"id", "rev", "fields"})
        _expect(isinstance(it["id"], int) and isinstance(it["rev"], int), f"ado {it.get('id')}: id and rev must be integers")
        _check_shape(f"ado {it['id']} fields", it["fields"], ADO_FIELDS, ADO_REQUIRED)
        _expect(it["fields"]["System.Id"] == it["id"], f"ado {it['id']}: System.Id must equal id")
    ids = {i["id"] for i in ado["value"]}
    _expect(len(ids) == len(ado["value"]), "ado: duplicate ids")
    _expect(len({i["fields"]["System.TeamProject"] for i in ado["value"]}) == 1, "ado: need at least one work item, all sharing one System.TeamProject")
    _expect(isinstance(ado["queries"], dict), "ado: queries must be an object keyed by query id")
    for qid, q in ado["queries"].items():
        _expect(UUID_RE.match(qid) is not None and qid == qid.lower(), f"ado query {qid!r}: id must be a lowercase uuid")
        _check_shape(f"ado query {qid}", q, {"name", "ids"}, {"name", "ids"})
        _expect(isinstance(q["ids"], list) and set(q["ids"]) <= ids, f"ado query {qid}: ids must exist in value[]")
    return {"jira": jira["issues"], "gitlab": gitlab, "ado": ado["value"], "ado_queries": ado["queries"]}


# ---- query helpers -----------------------------------------------------------------------------

def parse_query(raw: str) -> dict:
    out = {}
    for k, v in urllib.parse.parse_qsl(raw, keep_blank_values=True):
        if k in out:
            raise ApiError(400, f"duplicate query parameter {k!r}")
        out[k] = v
    return out


def allow_keys(q: dict, allowed: set) -> None:
    extra = sorted(set(q) - allowed)
    if extra:
        raise ApiError(400, f"unsupported query parameter(s) {extra}; allowed: {sorted(allowed)}")


def int_param(q: dict, name: str, default: int, lo: int, hi: int) -> int:
    raw = q.get(name)
    if raw is None:
        return default
    if not INT_RE.match(raw):
        raise ApiError(400, f"{name} must be a non-negative integer")
    n = int(raw)
    if not lo <= n <= hi:
        raise ApiError(400, f"{name} must be between {lo} and {hi}")
    return n


def apply_jql(issues: list, jql: str) -> list:
    jql = jql.strip()
    if not jql:
        return issues
    if not JQL_RE.match(jql):
        raise ApiError(400, "jql contains unsupported characters or is too long")
    jql = re.sub(r"\s+ORDER\s+BY\s+.*$", "", jql, flags=re.I)
    getters = {
        "project": lambda i: i["key"].rsplit("-", 1)[0],
        "status": lambda i: i["fields"]["status"]["name"],
        "statusCategory": lambda i: i["fields"]["status"]["statusCategory"]["name"],
        "issuetype": lambda i: i["fields"]["issuetype"]["name"],
    }
    getters["type"] = getters["issuetype"]
    for clause in re.split(r"\s+AND\s+", jql, flags=re.I):
        m = JQL_CLAUSE_RE.match(clause.strip())
        if not m:
            raise ApiError(400, f"unsupported jql clause; this fake accepts {sorted(getters)} with =, !=, IN, NOT IN joined by AND")
        field, op, raw = m.group(1), m.group(2).upper(), m.group(3)
        values = {v.strip("\"'").lower() for v in re.findall(JQL_VALUE, raw.strip("()"))}
        wanted = op in ("=", "IN")
        issues = [i for i in issues if (getters[field](i).lower() in values) == wanted]
    return issues


# ---- server ------------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "FakeTracker/1"
    sys_version = ""
    style = "generic"

    def log_request(self, code="-", size="-"):
        shown = " ".join(f"{h}=<redacted>" for h in REDACTED_HEADERS if self.headers.get(h))
        self.log_message('"%s" %s %s', self.requestline, code, shown)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - - [{self.log_date_time_string()}] {fmt % args}", file=self.server.log_stream, flush=True)

    def reply(self, status: int, body, extra: dict | None = None) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def error_body(self, message: str) -> dict:
        if self.style == "jira":
            return {"errorMessages": [message], "errors": {}}
        return {"message": message}

    def _read_only(self) -> None:
        self.style = "generic"
        self.reply(405, self.error_body(f"{self.command} is not allowed; this fake serves GET only"), {"Allow": "GET"})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _read_only

    def do_GET(self) -> None:
        self.style = "generic"
        try:
            status, body, extra = self.route()
        except ApiError as e:
            status, body, extra = e.status, self.error_body(e.message), {}
        except Exception as e:  # never drop the connection or leak a traceback to the client
            self.log_message("internal error: %s", type(e).__name__)
            status, body, extra = 500, self.error_body("internal error"), {}
        self.reply(status, body, extra)

    # -- auth --

    def require_token(self, kind: str) -> None:
        expected = self.server.token
        if kind == "gitlab":
            got = self.headers.get("PRIVATE-TOKEN", "")
        else:
            scheme, _, cred = self.headers.get("Authorization", "").partition(" ")
            got = ""
            if scheme == "Bearer":
                got = cred.strip()
            elif scheme == "Basic":
                try:
                    got = base64.b64decode(cred.strip(), validate=True).decode().partition(":")[2]
                except (binascii.Error, UnicodeDecodeError):
                    got = ""
        if not got or not hmac.compare_digest(got, expected):
            raise ApiError(401, "authentication failed: credential missing or not accepted (value not shown)")

    # -- routing --

    def route(self):
        if len(self.path) > MAX_PATH:
            raise ApiError(400, "request path too long")
        split = urllib.parse.urlsplit(self.path)
        segs = split.path.strip("/").split("/")
        if any(not SEGMENT_RE.match(s) for s in segs):
            raise ApiError(404, "unknown path")
        q = parse_query(split.query)
        fx = self.server.fixtures
        if segs[:3] == ["rest", "api", "2"]:
            self.style = "jira"
            self.require_token("jira")
            return self.jira(segs[3:], q, fx["jira"])
        if segs[:3] == ["rest", "agile", "1.0"]:
            self.style = "jira"
            self.require_token("jira")
            return self.jira_agile(segs[3:], q)
        if segs[:2] == ["api", "v4"]:
            self.style = "gitlab"
            self.require_token("gitlab")
            return self.gitlab(segs[2:], q, fx["gitlab"])
        if len(segs) >= 5 and segs[2:4] == ["_apis", "wit"]:
            self.style = "ado"
            self.require_token("ado")
            return self.ado(segs, q, fx["ado"], fx["ado_queries"])
        raise ApiError(404, "unknown path")

    def jira(self, segs, q, issues):
        base = self.server.base_url

        keep = JIRA_FIELDS
        if q.get("fields") not in (None, "*all"):  # Jira returns only the requested fields (key and id are always present)
            keep = set(q["fields"].split(",")) - {"key", "id"}
            if not keep <= JIRA_FIELDS:
                raise ApiError(400, f"unsupported fields; allowed: {sorted(JIRA_FIELDS)}")

        def with_self(i):
            return {"expand": "", "id": i["id"], "self": f"{base}/rest/api/2/issue/{i['id']}", "key": i["key"],
                    "fields": {k: v for k, v in i["fields"].items() if k in keep}}

        if segs == ["myself"]:
            allow_keys(q, {"expand"})
            return 200, dict(JIRA_ME, self=f"{base}/rest/api/2/user?username={JIRA_ME['name']}", avatarUrls={}, groups={"size": 0, "items": []},
                             applicationRoles={"size": 0, "items": []}, expand="groups,applicationRoles"), {}
        if segs == ["serverInfo"]:
            allow_keys(q, set())
            return 200, dict(JIRA_SERVER_INFO, baseUrl=base, serverTime=ASOF), {}
        if segs == ["project"]:
            allow_keys(q, {"expand", "recent"})
            keys = sorted({i["key"].rsplit("-", 1)[0] for i in issues})
            return 200, [{"expand": "description,lead", "self": f"{base}/rest/api/2/project/{n}", "id": str(10000 + n), "key": k,
                          "name": f"Project {k}", "projectTypeKey": "software", "avatarUrls": {}} for n, k in enumerate(keys)], {}
        if segs == ["field"]:
            allow_keys(q, set())
            return 200, [{"id": f, "name": f.capitalize(), "custom": False, "orderable": True, "navigable": True, "searchable": True,
                          "clauseNames": [f], "schema": {"type": "string", "system": f}} for f in sorted(JIRA_FIELDS)], {}
        if len(segs) == 4 and segs[:2] == ["issue", "createmeta"] and segs[3] == "issuetypes":
            allow_keys(q, {"expand", "startAt", "maxResults"})
            names = sorted({i["fields"]["issuetype"]["name"] for i in issues if i["key"].rsplit("-", 1)[0] == segs[2]})
            if not names:
                raise ApiError(404, "Project does not exist or you do not have permission to see it.")
            values = [{"self": f"{base}/rest/api/2/issuetype/{n}", "id": str(n), "name": k, "subtask": False} for n, k in enumerate(names, 1)]
            return 200, {"maxResults": 50, "startAt": 0, "total": len(values), "values": values}, {}
        if segs == ["search"]:
            allow_keys(q, {"jql", "startAt", "maxResults", "fields", "expand", "validateQuery"})
            start = int_param(q, "startAt", 0, 0, MAX_START_AT)
            size = int_param(q, "maxResults", 50, 1, MAX_PAGE_SIZE)
            hits = apply_jql(issues, q.get("jql", ""))
            page = [with_self(i) for i in hits[start:start + size]]
            return 200, {"expand": "names,schema", "startAt": start, "maxResults": size, "total": len(hits), "issues": page}, {}
        if len(segs) == 2 and segs[0] == "issue":
            allow_keys(q, {"fields", "expand"})
            for i in issues:
                if segs[1] in (i["key"], i["id"]):
                    return 200, with_self(i), {}
            raise ApiError(404, "Issue does not exist or you do not have permission to see it.")
        raise ApiError(404, "unknown path")

    def jira_agile(self, segs, q):
        if segs == ["board"]:  # no boards in the fake: a CLI must cope with an empty, complete page
            allow_keys(q, {"projectKeyOrId", "type", "name", "startAt", "maxResults"})
            return 200, {"maxResults": 50, "startAt": 0, "total": 0, "isLast": True, "values": []}, {}
        raise ApiError(404, "unknown path")

    def gitlab(self, segs, q, issues):
        if len(segs) not in (3, 4) or segs[0] != "projects" or segs[2] != "issues":
            raise ApiError(404, "404 Not Found")
        if urllib.parse.unquote(segs[1]) != str(issues[0]["project_id"]):
            raise ApiError(404, "404 Project Not Found")
        if len(segs) == 4:
            allow_keys(q, set())
            if not INT_RE.match(segs[3]):
                raise ApiError(400, "issue iid must be an integer")
            for i in issues:
                if i["iid"] == int(segs[3]):
                    return 200, i, {}
            raise ApiError(404, "404 Not found")
        allow_keys(q, {"page", "per_page", "state"})
        page = int_param(q, "page", 1, 1, MAX_PAGES)
        per_page = int_param(q, "per_page", 20, 1, MAX_PAGE_SIZE)
        state = q.get("state", "all")
        if state not in GITLAB_STATES:
            raise ApiError(400, f"state must be one of {list(GITLAB_STATES)}")
        hits = [i for i in issues if state == "all" or i["state"] == state]
        pages = max(1, -(-len(hits) // per_page))
        headers = {
            "X-Total": str(len(hits)), "X-Total-Pages": str(pages), "X-Page": str(page), "X-Per-Page": str(per_page),
            "X-Next-Page": str(page + 1) if page < pages else "", "X-Prev-Page": str(page - 1) if page > 1 else "",
        }
        return 200, hits[(page - 1) * per_page:page * per_page], headers

    def ado(self, segs, q, items, queries):
        org, project = segs[0], urllib.parse.unquote(segs[1])
        if project.lower() != items[0]["fields"]["System.TeamProject"].lower():
            raise ApiError(404, "project not found")
        base = f"{self.server.base_url}/{org}"

        def url(i):
            return f"{base}/_apis/wit/workItems/{i}"

        if segs[4:] == ["workitems"]:
            allow_keys(q, {"ids", "api-version", "fields"})
            self.api_version(q)
            ids = q.get("ids", "")
            if not IDS_RE.match(ids):
                raise ApiError(400, "ids must be a comma-separated list of 1-200 integers")
            wanted = [int(x) for x in ids.split(",")]
            fields = q.get("fields")
            keep = set(ADO_FIELDS)
            if fields is not None:
                keep = set(fields.split(","))
                if not keep <= ADO_FIELDS:
                    raise ApiError(400, f"unsupported fields; allowed: {sorted(ADO_FIELDS)}")
            by_id = {i["id"]: i for i in items}
            missing = [i for i in wanted if i not in by_id]
            if missing:
                raise ApiError(404, f"work item {missing[0]} does not exist")
            value = [{"id": i, "rev": by_id[i]["rev"], "fields": {k: v for k, v in by_id[i]["fields"].items() if k in keep}, "url": url(i)} for i in wanted]
            return 200, {"count": len(value), "value": value}, {}
        if len(segs) == 6 and segs[4] == "wiql":
            allow_keys(q, {"api-version", "$top", "timePrecision"})
            self.api_version(q)
            top = int_param(q, "$top", 0, 1, 200)  # omitted: the whole result, like the service
            qid = segs[5].lower()
            if not UUID_RE.match(qid) or qid not in queries:
                raise ApiError(404, "query not found")
            hits = queries[qid]["ids"][:top] if top else queries[qid]["ids"]
            columns = [{"referenceName": c, "name": c.rsplit(".", 1)[1], "url": f"{base}/_apis/wit/fields/{c}"} for c in ADO_COLUMNS]
            return 200, {"queryType": "flat", "queryResultType": "workItem", "asOf": ASOF, "columns": columns,
                         "workItems": [{"id": i, "url": url(i)} for i in hits]}, {}
        raise ApiError(404, "unknown path")

    @staticmethod
    def api_version(q):
        if q.get("api-version") != "7.1":
            raise ApiError(400, "api-version=7.1 is required")


class FakeTrackerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, fixtures: dict, port: int = 0, token: str | None = None):
        super().__init__(("127.0.0.1", port), Handler)
        self.fixtures = fixtures
        self.log_stream = sys.stderr
        self.token = token or os.environ.get("FAKE_TRACKER_TOKEN") or DEFAULT_TOKEN_VALUE
        if not TOKEN_RE.match(self.token):
            self.server_close()
            raise SystemExit("FAKE_TRACKER_TOKEN must be 8-128 characters from [A-Za-z0-9._-]")

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=0, help="TCP port on 127.0.0.1; 0 (default) picks a free one")
    ap.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="folder with jira_issues.json, gitlab_issues.json, ado_workitems.json")
    a = ap.parse_args(argv)
    if not 0 <= a.port <= 65535:
        sys.exit("--port must be 0-65535")
    server = FakeTrackerServer(load_fixtures(a.fixtures), a.port)
    print(server.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
