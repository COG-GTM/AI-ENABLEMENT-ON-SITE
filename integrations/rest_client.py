#!/usr/bin/env python3
"""Read-only REST client for Jira, Confluence, GitLab, GitHub, and Azure DevOps. Standard library only.

    python integrations/rest_client.py jira search "project = SN AND status = Open"
    python integrations/rest_client.py jira issue SN-42
    python integrations/rest_client.py gitlab issues 123            # project id, or path like group/project
    python integrations/rest_client.py gitlab mrs group/project
    python integrations/rest_client.py github issues owner/repo
    python integrations/rest_client.py ado query 00000000-0000-4000-8000-000000000001   # saved WIQL query id
    python integrations/rest_client.py ado workitems 101,102,103
    python integrations/rest_client.py confluence search "space = ENG AND title ~ ICD"
    python integrations/rest_client.py --dry-run jira issue SN-42   # print the request, send nothing

Configuration is environment variables only (see integrations/README.md):
  JIRA_BASE, JIRA_TOKEN, JIRA_EMAIL (Cloud only; leave unset for Data Center PAT)
  CONF_BASE (defaults to JIRA_BASE), GITLAB_BASE, GITLAB_TOKEN, GITHUB_BASE (default api.github.com),
  GITHUB_TOKEN, ADO_ORG, ADO_PROJECT, ADO_TOKEN
Optional: REST_CA_BUNDLE=/path/to/ca.pem for a private certificate authority.

Only GET is used. Azure DevOps ad-hoc WIQL is a POST, so it is not offered; run a saved query by id instead.
List commands (jira search, gitlab issues/mrs) fetch every page before returning, so the output is complete
or the command fails; nothing is filtered on page 1. github issues returns the first MAX_RESULTS open issues only
(there is no offline fake for GitHub, so its page walk is not exercised here).
HTTPS is required, except plain HTTP to 127.0.0.1 for the offline fake (integrations/fake_server.py).
Output is JSON on stdout. Extend by adding a function to COMMANDS; keep it GET-only.
"""

import argparse
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_S = 30
MAX_RESULTS = 50
MAX_PAGES = 20  # list commands walk every page up to this many, then stop with an error rather than a partial file
JIRA_FIELDS = "key,summary,description,status,priority,issuetype,components,labels,created,resolutiondate"  # what tracker_import reads
ID_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._ -]{1,64}$")  # Azure DevOps project names may contain spaces
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
IDS_RE = re.compile(r"^[0-9]{1,10}(,[0-9]{1,10}){0,199}$")  # Azure DevOps work item ids are int32


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        sys.exit(f"missing environment variable {name} (see integrations/README.md)")
    return v.rstrip("/")


def check_id(value: str) -> str:
    if not ID_RE.match(value):
        sys.exit(f"invalid identifier: {value!r}")
    return value


def basic(user: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()


def local_http(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    return u.scheme == "http" and u.hostname == "127.0.0.1"


def fetch(url: str, headers: dict, dry_run: bool):
    """GET url; return (json body, response headers as a case-insensitive HTTPMessage). Dry run prints the request and returns (None, {})."""
    if not url.startswith("https://") and not local_http(url):
        sys.exit("refusing non-HTTPS URL; TLS is required (plain HTTP is allowed only to 127.0.0.1)")
    if dry_run:
        shown = {k: ("<redacted>" if k.lower() in ("authorization", "private-token") else v) for k, v in headers.items()}
        print(json.dumps({"method": "GET", "url": url, "headers": shown, "body": None}, indent=2))
        return None, {}
    req = urllib.request.Request(url, method="GET", headers={**headers, "Accept": "application/json"})
    ctx = None
    if not local_http(url):
        ctx = ssl.create_default_context(cafile=os.environ.get("REST_CA_BUNDLE") or None)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
            return json.load(r), r.headers
    except urllib.error.HTTPError as e:
        e.close()
        sys.exit(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}; check token scope and host")
    except urllib.error.URLError as e:
        sys.exit(f"connection failed: {e.reason}")
    except ValueError:
        sys.exit(f"non-JSON response from {urllib.parse.urlsplit(url).netloc}")


def request(url: str, headers: dict, dry_run: bool):
    return fetch(url, headers, dry_run)[0]


def too_many_pages(what: str, got: int):
    sys.exit(f"{what}: more than {MAX_PAGES} pages ({got} items so far); narrow the query instead of importing a partial list")


# ---- Jira -------------------------------------------------------------------------------------

def jira_headers() -> dict:
    token = env("JIRA_TOKEN")
    email = os.environ.get("JIRA_EMAIL")
    return {"Authorization": basic(email, token) if email else f"Bearer {token}"}


def jira_search(args, dry):
    """Walk every page and return one search response.

    v2 (Data Center): startAt/total. Cloud v3 search/jql: nextPageToken/isLast, see
    https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
    """
    cloud = bool(os.environ.get("JIRA_EMAIL"))
    base = env("JIRA_BASE") + ("/rest/api/3/search/jql?" if cloud else "/rest/api/2/search?")
    params = {"jql": args.query, "maxResults": MAX_RESULTS, "fields": JIRA_FIELDS}
    issues, token, start = [], None, 0
    for _ in range(MAX_PAGES):
        page_params = dict(params, **({"nextPageToken": token} if token else {})) if cloud else dict(params, startAt=start)
        body = request(base + urllib.parse.urlencode(page_params), jira_headers(), dry)
        if body is None:
            return None
        page = body.get("issues") if isinstance(body, dict) else None
        if not isinstance(page, list):
            sys.exit("unexpected Jira search response: no issues[]")
        issues.extend(page)
        if cloud:
            token = body.get("nextPageToken")
            if body.get("isLast", True) or not isinstance(token, str) or not page:
                break
        else:
            total = body.get("total")
            if not isinstance(total, int):
                sys.exit("unexpected Jira search response: no integer total")
            start += len(page)
            if not page or start >= total:
                break
    else:
        too_many_pages("jira search", len(issues))
    return {"startAt": 0, "maxResults": len(issues), "total": len(issues), "issues": issues}


def jira_issue(args, dry):
    key = check_id(args.query)
    return request(f"{env('JIRA_BASE')}/rest/api/2/issue/{key}", jira_headers(), dry)


def confluence_search(args, dry):
    base = os.environ.get("CONF_BASE") or env("JIRA_BASE")
    q = urllib.parse.urlencode({"cql": args.query, "limit": MAX_RESULTS})
    return request(f"{base.rstrip('/')}/rest/api/content/search?{q}", jira_headers(), dry)


# ---- GitLab -----------------------------------------------------------------------------------

def gitlab_list(project: str, kind: str, state: str, dry):
    """Follow X-Next-Page until it is empty (https://docs.gitlab.com/api/rest/#pagination) and return the full list."""
    project = urllib.parse.quote(check_id(project), safe="")
    items, page = [], 1
    for _ in range(MAX_PAGES):
        q = urllib.parse.urlencode({"state": state, "per_page": MAX_RESULTS, "page": page})
        body, hdrs = fetch(f"{env('GITLAB_BASE')}/api/v4/projects/{project}/{kind}?{q}", {"PRIVATE-TOKEN": env("GITLAB_TOKEN")}, dry)
        if body is None:
            return None
        if not isinstance(body, list):
            sys.exit(f"unexpected GitLab {kind} response: not a list")
        items.extend(body)
        nxt = hdrs.get("X-Next-Page", "")
        if not nxt or not body:
            return items
        if not nxt.isdigit() or int(nxt) != page + 1:
            sys.exit("unexpected X-Next-Page header from GitLab")
        page += 1
    too_many_pages(f"gitlab {kind}", len(items))


def gitlab_issues(args, dry):
    return gitlab_list(args.query, "issues", "all", dry)  # open and closed, so a tracker import sees both


def gitlab_mrs(args, dry):
    return gitlab_list(args.query, "merge_requests", "opened", dry)


# ---- GitHub -----------------------------------------------------------------------------------

def github_issues(args, dry):
    repo = check_id(args.query)
    if repo.count("/") != 1:
        sys.exit("expected owner/repo")
    q = urllib.parse.urlencode({"state": "open", "per_page": MAX_RESULTS})
    return request(f"{env('GITHUB_BASE', 'https://api.github.com')}/repos/{repo}/issues?{q}",
                   {"Authorization": f"Bearer {env('GITHUB_TOKEN')}", "X-GitHub-Api-Version": "2022-11-28"}, dry)


# ---- Azure DevOps -----------------------------------------------------------------------------

def ado_base() -> str:
    project = env("ADO_PROJECT")
    if not PROJECT_NAME_RE.match(project):
        sys.exit("invalid ADO_PROJECT name")
    return f"{env('ADO_ORG')}/{urllib.parse.quote(project)}/_apis/wit"


def ado_query(args, dry):
    if not UUID_RE.match(args.query):
        sys.exit("expected a saved query id (uuid); ad-hoc WIQL needs POST and is not offered")
    url = f"{ado_base()}/wiql/{args.query}?api-version=7.1&$top={MAX_RESULTS}"
    return request(url, {"Authorization": basic("", env("ADO_TOKEN"))}, dry)


def ado_workitems(args, dry):
    if not IDS_RE.match(args.query):
        sys.exit("expected comma-separated work item ids, e.g. 101,102")
    url = f"{ado_base()}/workitems?ids={args.query}&api-version=7.1"
    return request(url, {"Authorization": basic("", env("ADO_TOKEN"))}, dry)


COMMANDS = {
    ("jira", "search"): jira_search,
    ("jira", "issue"): jira_issue,
    ("confluence", "search"): confluence_search,
    ("gitlab", "issues"): gitlab_issues,
    ("gitlab", "mrs"): gitlab_mrs,
    ("github", "issues"): github_issues,
    ("ado", "query"): ado_query,
    ("ado", "workitems"): ado_workitems,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the request; do not send it")
    ap.add_argument("system", choices=sorted({s for s, _ in COMMANDS}))
    ap.add_argument("action")
    ap.add_argument("query", help="JQL / CQL / key / project id / owner/repo / saved query id / work item ids")
    args = ap.parse_args(argv)
    if len(args.query) > 2000:
        sys.exit("query too long")
    fn = COMMANDS.get((args.system, args.action))
    if fn is None:
        sys.exit(f"unknown action; available: {sorted(a for s, a in COMMANDS if s == args.system)}")
    result = fn(args, args.dry_run)
    if result is not None:
        json.dump(result, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
