#!/usr/bin/env python3
"""Read-only REST client for Jira, Confluence, GitLab, GitHub, and Azure DevOps. Standard library only.

    python integrations/rest_client.py jira search "project = SN AND status = Open"
    python integrations/rest_client.py jira issue SN-42
    python integrations/rest_client.py gitlab issues 123            # project id, or path like group/project
    python integrations/rest_client.py gitlab mrs group/project
    python integrations/rest_client.py github issues owner/repo
    python integrations/rest_client.py ado wiql "SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Active'"
    python integrations/rest_client.py confluence search "space = ENG AND title ~ ICD"
    python integrations/rest_client.py --dry-run jira issue SN-42   # print the request, send nothing

Configuration is environment variables only (see integrations/README.md):
  JIRA_BASE, JIRA_TOKEN, JIRA_EMAIL (Cloud only; leave unset for Data Center PAT)
  CONF_BASE (defaults to JIRA_BASE), GITLAB_BASE, GITLAB_TOKEN, GITHUB_BASE (default api.github.com),
  GITHUB_TOKEN, ADO_ORG, ADO_PROJECT, ADO_TOKEN
Optional: REST_CA_BUNDLE=/path/to/ca.pem for a private certificate authority.

Only GET is used, except Azure DevOps WIQL which is a POST that reads. Output is JSON on stdout.
Extend by adding a function to COMMANDS; keep it read-only.
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
ID_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._ -]{1,64}$")  # Azure DevOps project names may contain spaces


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


def request(method: str, url: str, headers: dict, body: dict | None, dry_run: bool):
    if not url.startswith("https://"):
        sys.exit("refusing non-HTTPS URL; TLS is required")
    data = json.dumps(body).encode() if body is not None else None
    if dry_run:
        shown = {k: ("<redacted>" if k.lower() in ("authorization", "private-token") else v) for k, v in headers.items()}
        print(json.dumps({"method": method, "url": url, "headers": shown, "body": body}, indent=2))
        return None
    req = urllib.request.Request(url, data=data, method=method, headers={**headers, "Accept": "application/json"})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context(cafile=os.environ.get("REST_CA_BUNDLE") or None)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}; check token scope and host")
    except urllib.error.URLError as e:
        sys.exit(f"connection failed: {e.reason}")


# ---- Jira -------------------------------------------------------------------------------------

def jira_headers() -> dict:
    token = env("JIRA_TOKEN")
    email = os.environ.get("JIRA_EMAIL")
    return {"Authorization": basic(email, token) if email else f"Bearer {token}"}


def jira_search(args, dry):
    cloud = bool(os.environ.get("JIRA_EMAIL"))
    q = urllib.parse.urlencode({"jql": args.query, "maxResults": MAX_RESULTS, "fields": "key,summary,status,priority,issuetype"})
    path = "/rest/api/3/search/jql?" if cloud else "/rest/api/2/search?"
    return request("GET", env("JIRA_BASE") + path + q, jira_headers(), None, dry)


def jira_issue(args, dry):
    key = check_id(args.query)
    return request("GET", f"{env('JIRA_BASE')}/rest/api/2/issue/{key}", jira_headers(), None, dry)


def confluence_search(args, dry):
    base = os.environ.get("CONF_BASE") or env("JIRA_BASE")
    q = urllib.parse.urlencode({"cql": args.query, "limit": MAX_RESULTS})
    return request("GET", f"{base.rstrip('/')}/rest/api/content/search?{q}", jira_headers(), None, dry)


# ---- GitLab -----------------------------------------------------------------------------------

def gitlab_issues(args, dry):
    project = urllib.parse.quote(check_id(args.query), safe="")
    q = urllib.parse.urlencode({"state": "opened", "per_page": MAX_RESULTS})
    return request("GET", f"{env('GITLAB_BASE')}/api/v4/projects/{project}/issues?{q}",
                   {"PRIVATE-TOKEN": env("GITLAB_TOKEN")}, None, dry)


def gitlab_mrs(args, dry):
    project = urllib.parse.quote(check_id(args.query), safe="")
    q = urllib.parse.urlencode({"state": "opened", "per_page": MAX_RESULTS})
    return request("GET", f"{env('GITLAB_BASE')}/api/v4/projects/{project}/merge_requests?{q}",
                   {"PRIVATE-TOKEN": env("GITLAB_TOKEN")}, None, dry)


# ---- GitHub -----------------------------------------------------------------------------------

def github_issues(args, dry):
    repo = check_id(args.query)
    if repo.count("/") != 1:
        sys.exit("expected owner/repo")
    q = urllib.parse.urlencode({"state": "open", "per_page": MAX_RESULTS})
    return request("GET", f"{env('GITHUB_BASE', 'https://api.github.com')}/repos/{repo}/issues?{q}",
                   {"Authorization": f"Bearer {env('GITHUB_TOKEN')}", "X-GitHub-Api-Version": "2022-11-28"}, None, dry)


# ---- Azure DevOps -----------------------------------------------------------------------------

def ado_wiql(args, dry):
    if not args.query.lstrip().upper().startswith("SELECT"):
        sys.exit("WIQL must be a SELECT query")
    project = env("ADO_PROJECT")
    if not PROJECT_NAME_RE.match(project):
        sys.exit("invalid ADO_PROJECT name")
    url = f"{env('ADO_ORG')}/{urllib.parse.quote(project)}/_apis/wit/wiql?api-version=7.1&$top={MAX_RESULTS}"
    return request("POST", url, {"Authorization": basic("", env("ADO_TOKEN"))}, {"query": args.query}, dry)


COMMANDS = {
    ("jira", "search"): jira_search,
    ("jira", "issue"): jira_issue,
    ("confluence", "search"): confluence_search,
    ("gitlab", "issues"): gitlab_issues,
    ("gitlab", "mrs"): gitlab_mrs,
    ("github", "issues"): github_issues,
    ("ado", "wiql"): ado_wiql,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the request; do not send it")
    ap.add_argument("system", choices=sorted({s for s, _ in COMMANDS}))
    ap.add_argument("action")
    ap.add_argument("query", help="JQL / CQL / key / project id / owner/repo / WIQL")
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
