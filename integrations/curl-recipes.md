# curl recipes (read-only)

Set the variables for your session; never write values into files. Replace hosts with yours.
Every call below only reads. Add `-sS` for quiet output and pipe to `python -m json.tool` to pretty-print.

```bash
export JIRA_BASE="https://jira.example.internal"        # Cloud: https://<site>.atlassian.net
export JIRA_TOKEN="<paste at runtime>"
export JIRA_EMAIL="<cloud only>"
export GITLAB_BASE="https://gitlab.example.internal"
export GITLAB_TOKEN="<paste at runtime>"
export GITHUB_BASE="https://api.github.com"              # GHES: https://<host>/api/v3
export GITHUB_TOKEN="<paste at runtime>"
export ADO_ORG="https://dev.azure.com/<org>"
export ADO_TOKEN="<paste at runtime>"
export CONF_BASE="https://confluence.example.internal"   # Cloud: https://<site>.atlassian.net/wiki
```

## Jira

Data Center (PAT, Bearer):
```bash
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_BASE/rest/api/2/search?jql=project%3DSN%20AND%20status%3DOpen&maxResults=20&fields=key,summary,status,priority"
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/issue/SN-42"
```

Cloud (API token, Basic email:token):
```bash
curl -sS -u "$JIRA_EMAIL:$JIRA_TOKEN" \
  "$JIRA_BASE/rest/api/3/search/jql?jql=project%3DSN%20AND%20status%3DOpen&maxResults=20&fields=key,summary,status"
curl -sS -u "$JIRA_EMAIL:$JIRA_TOKEN" "$JIRA_BASE/rest/api/3/issue/SN-42/comment"
```

Sanity check that the token works: `curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/myself"`.

## Confluence

```bash
# Data Center
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" \
  "$CONF_BASE/rest/api/content/search?cql=space%3DENG%20AND%20title~%22ICD%22&limit=10"
# Cloud
curl -sS -u "$JIRA_EMAIL:$JIRA_TOKEN" "$CONF_BASE/api/v2/pages?space-id=<id>&limit=10"
```

## GitLab

```bash
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$GITLAB_BASE/api/v4/projects?membership=true&simple=true&per_page=20"
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$GITLAB_BASE/api/v4/projects/<id>/issues?state=opened&per_page=20"
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$GITLAB_BASE/api/v4/projects/<id>/merge_requests?state=opened"
```

## GitHub / GitHub Enterprise Server

```bash
curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" \
  "$GITHUB_BASE/repos/<owner>/<repo>/issues?state=open&per_page=20"
curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" "$GITHUB_BASE/repos/<owner>/<repo>/pulls?state=open"
```

## Azure DevOps Services

```bash
# Basic auth with empty user; curl base64-encodes ":$ADO_TOKEN" for you
curl -sS -u ":$ADO_TOKEN" "$ADO_ORG/_apis/projects?api-version=7.1"
# Run a saved query by its id (Boards > Queries > copy the id from the URL), then fetch the work items it lists
curl -sS -u ":$ADO_TOKEN" "$ADO_ORG/<project>/_apis/wit/wiql/<query-id>?api-version=7.1&\$top=50"
curl -sS -u ":$ADO_TOKEN" "$ADO_ORG/<project>/_apis/wit/workitems?ids=101,102,103&api-version=7.1"
```
Ad-hoc WIQL text needs a `POST`, so it is not used here; save the query in Azure DevOps and read it by id.

## Pagination and rate limits

Jira: `startAt`/`maxResults` (Cloud v3 `nextPageToken`). GitLab and GitHub: `page`/`per_page`, follow `Link` headers.
Azure DevOps: `$top`/`continuationToken`. Fetch every page before filtering or counting.

## Turning results into repository artifacts

Save the JSON under `outputs/`, then `python tools/tracker_import.py --from jira|gitlab|ado --in outputs/<file>.json --out outputs/tracker.json`
and `python tools/tracker_report.py --file outputs/tracker.json` give you the same report and deck inputs
as the offline tracker. To practice without a token, see "Prove it offline" in `README.md`.
