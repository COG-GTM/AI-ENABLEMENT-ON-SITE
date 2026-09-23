# Connecting Devin to your tools (Jira, GitLab, Confluence, GitHub, Azure DevOps)

Four ways to reach an external system, cheapest first. Start at the top; move down only when you
need to and your administrator has approved it. Everything here is read-only by default.

| Lane | What it is | Auth | Needs network | Needs install | Use when |
| --- | --- | --- | --- | --- | --- |
| 1. Offline | Work from files already in the repository (`example-system/tracker.json`, exported CSV/JSON) or the fake tracker server below | none | no | nothing | Always works. Default for practice and walkthroughs. |
| 2. REST / curl | Devin calls the vendor HTTP API with `curl` or `rest_client.py` | PAT or API token in an env var | yes, to the vendor host | `curl` (present) or Python 3 | You have a token and want the fewest moving parts. |
| 3. Vendor CLI | `glab`, `gh`, `az devops`, `acli` run by Devin | the CLI's own login (token or browser) | yes | the CLI binary | The CLI is already installed and approved on the laptop. |
| 4. MCP server | Tools show up inside Devin. Either a process Devin starts on the laptop (stdio) or a URL your team or a vendor hosts (HTTPS); see `mcp-hosting.md` | env var / secret file for local; token header or browser sign-in for hosted | local: only if the server calls out; hosted: yes | local: a runtime (Python/Node/Go) or binary; hosted: nothing on the laptop | You want the tools available in every session without re-explaining the API. |

Transport (CLI, REST, MCP) is separate from authentication (PAT, API token, OAuth). Any lane can
use any auth the vendor supports.

## Authentication cheat sheet

| Vendor | Token type | Header / flag | Where to create | Notes |
| --- | --- | --- | --- | --- |
| Jira / Confluence Cloud | API token (per user) | `Authorization: Basic base64(email:token)` | Atlassian account settings, Security | Survives SAML/SSO unless the admin disables API tokens. Scoped tokens preferred. |
| Jira / Confluence Data Center | PAT | `Authorization: Bearer $TOKEN` | Profile, Personal Access Tokens | On-premises. No official MCP; use REST. |
| GitLab (SaaS or self-managed) | PAT, scope `read_api` | `PRIVATE-TOKEN: $TOKEN` | User settings, Access tokens | `glab auth login --token` for the CLI. GitLab's built-in MCP is OAuth and must be enabled by the admin. |
| GitHub / GHES | Fine-grained PAT, read-only | `Authorization: Bearer $TOKEN` | Settings, Developer settings | `gh auth login` for the CLI. `github-mcp-server` accepts the same PAT. |
| Azure DevOps Services | PAT, scope Work Items (Read) | `Authorization: Basic base64(:token)` | User settings, Personal access tokens | `az devops` CLI uses `AZURE_DEVOPS_EXT_PAT`. Azure DevOps Server (on-prem) differs. |
| OAuth (any vendor) | browser sign-in through your IdP | handled by the client | admin enables the app | Needed for vendor-hosted MCP servers (`devin mcp login <name>`). Requires admin approval; see `mcp-hosting.md`, model D. |

Least privilege: read scopes only, one token per tool, short expiry, never paste a token into a chat
or a file. Set it in the shell for the session: `export JIRA_TOKEN=...` (Windows: `$env:JIRA_TOKEN="..."`).

## Files in this folder

| File | Lane | What it does |
| --- | --- | --- |
| `curl-recipes.md` | 2 | Copy-paste read-only `curl` calls for each vendor, env vars only. |
| `rest_client.py` | 2 | Standard-library Python client: `python integrations/rest_client.py jira search "project = SN"`. `--dry-run` prints the request without sending. |
| `cli-recipes.md` | 3 | Read-only `glab`, `gh`, `az devops`, `acli` commands and how they log in. |
| `test_rest_client.py` | 2 | Offline tests: every command dry-runs, tokens are redacted, bad input is refused. |
| `fake_server.py` | 1 | Offline stand-in for the Jira, GitLab, and Azure DevOps read endpoints on `127.0.0.1`, fed by `fixtures/`. See "Prove it offline". |
| `fixtures/` | 1 | Twelve synthetic sensor-node issues, once per vendor shape (`jira_issues.json`, `gitlab_issues.json`, `ado_workitems.json`) plus `csv_export.csv`. |
| `../tools/tracker_import.py` | 1-2 | Normalises a vendor export (fake or real) or a CSV into the tracker schema; `../tools/tests/test_integrations.py` drives server and importer. |
| `mcp-hosting.md` | 4 | Where an MCP server can live (your laptop, shared entry with personal secret, team-hosted, vendor-hosted), what changes between them, and the questions Devin asks before writing config. Start here for anything beyond the reference server. |
| `mcp_config.example.json` | 4 | One entry per hosting model to copy into `.devin/mcp_config.json`: the local reference server, two local vendor servers, a team-hosted URL, a disabled vendor-hosted URL (delete what you do not use). |
| `reference-mcp/server.py` | 4 | A complete MCP server in one file, no dependencies, exposing three read-only tools over `example-system/`. Already registered in `.devin/mcp_config.json`. |
| `reference-mcp/handshake.jsonl`, `reference-mcp/test_server.py` | 4 | Five-line protocol walkthrough and the tests that drive the server over a real pipe. |
| `mcp-overview.html`, `mcp-overview.deck.json` | 4 | A 16-slide briefing on the same material for a mixed room of leadership and engineers: what MCP is, the four hosting models with pros and cons, where secrets go, and what is not proven here. Open the HTML in a browser (arrow keys, `P` prints to PDF); edit the outline and rebuild with `python tools/build_deck.py integrations/mcp-overview.deck.json integrations/mcp-overview.html`. |

## Prove it offline

The whole "connect a tool" path, with no network and no real token. Terminal 1:

```bash
python integrations/fake_server.py            # prints the port it picked, e.g. 41231; Ctrl-C stops it
# or: FAKE_TRACKER_TOKEN=my-practice-token python integrations/fake_server.py --port 8089 --fixtures integrations/fixtures
```

Terminal 2 (`PORT` is the number printed above; the token defaults to the constant in `fake_server.py`):

```bash
export PORT=41231 FAKE_TRACKER_TOKEN=fake-token-for-local-tests
# Jira: paginated search (startAt/maxResults/total/issues[]) and one issue
curl -sS -H "Authorization: Bearer $FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/rest/api/2/search?jql=project+%3D+SN&startAt=0&maxResults=5" > outputs/jira-page1.json
curl -sS -H "Authorization: Bearer $FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/rest/api/2/issue/SN-103"
# GitLab: X-Total / X-Page / X-Per-Page / X-Next-Page headers drive the page walk
curl -sS -D outputs/gitlab-headers.txt -H "PRIVATE-TOKEN: $FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/api/v4/projects/123/issues?state=all&page=1&per_page=5" > outputs/gitlab-page1.json
curl -sS -H "PRIVATE-TOKEN: $FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/api/v4/projects/123/issues/7"
# Azure DevOps: saved query by id (GET), then the work items it lists
curl -sS -u ":$FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/sn-org/sensor-node/_apis/wit/wiql/00000000-0000-4000-8000-000000000001?api-version=7.1"
curl -sS -u ":$FAKE_TRACKER_TOKEN" "http://127.0.0.1:$PORT/sn-org/sensor-node/_apis/wit/workitems?ids=101,102,103&api-version=7.1" > outputs/ado-items.json
```

`rest_client.py` works the same way; point its base URL at the fake (plain HTTP is accepted for `127.0.0.1` only):

```bash
JIRA_BASE=http://127.0.0.1:$PORT JIRA_TOKEN=$FAKE_TRACKER_TOKEN python integrations/rest_client.py jira search "project = SN" > outputs/jira-all.json
GITLAB_BASE=http://127.0.0.1:$PORT GITLAB_TOKEN=$FAKE_TRACKER_TOKEN python integrations/rest_client.py gitlab issues 123 > outputs/gitlab-all.json
ADO_ORG=http://127.0.0.1:$PORT/sn-org ADO_PROJECT=sensor-node ADO_TOKEN=$FAKE_TRACKER_TOKEN python integrations/rest_client.py ado workitems 101,102,103
```

Import what you fetched (or a fixture directly), then report on it exactly like the offline tracker.
`rest_client.py jira search` and `gitlab issues` fetch every page (open and closed) before printing and stop with an error past 20 pages instead of writing a partial file; with `curl`, fetch every page yourself before importing. The importer works on what it is given and does not page.

```bash
python tools/tracker_import.py --from jira   --in outputs/jira-all.json                    --out outputs/tracker-jira.json
python tools/tracker_import.py --from gitlab --in outputs/gitlab-all.json                  --out outputs/tracker-gitlab.json
python tools/tracker_import.py --from ado    --in integrations/fixtures/ado_workitems.json --out outputs/tracker-ado.json
python tools/tracker_import.py --from csv    --in integrations/fixtures/csv_export.csv     --out outputs/tracker-csv.json
python tools/tracker_import.py --from jira   --in outputs/jira-all.json --out outputs/tracker-merged.json --merge example-system/tracker.json
python tools/tracker_report.py --file outputs/tracker-jira.json --markdown
```

What the fake does and does not do:

- Binds `127.0.0.1` only; `--port` defaults to an ephemeral port (0) and is printed as the only line on stdout.
- Auth: Jira and Azure DevOps paths take `Authorization: Bearer <token>` or `Authorization: Basic base64(user:token)`; GitLab paths take `PRIVATE-TOKEN`. The accepted value is `$FAKE_TRACKER_TOKEN` (default in `fake_server.py`). Missing or wrong -> `401` JSON, and the value is never echoed or logged.
- Endpoints: `/rest/api/2/search` (`jql`, `startAt`, `maxResults`, `fields`), `/rest/api/2/issue/{key}`, `/api/v4/projects/{id}/issues` (`page`, `per_page`, `state`), `/api/v4/projects/{id}/issues/{iid}`, `/{org}/{project}/_apis/wit/workitems` (`ids`, `api-version`, `fields`), `/{org}/{project}/_apis/wit/wiql/{query-id}` (`api-version`, `$top`).
- Unknown path or id -> `404` JSON. Unknown, non-integer, negative, or oversized query parameters -> `400` JSON. Any method other than GET -> `405` with `Allow: GET`; there is no write path, and `test_integrations.py` asserts that.
- Azure DevOps ad-hoc WIQL is a POST in the real API, so the fake (and `rest_client.py ado query`) serve only the GET saved-query-by-id form. Save the query in Azure DevOps first.
- Field names and pagination follow the public vendor docs cited at the top of `fake_server.py`. Only the read-only subset above exists; anything else is `404`.
- The importer maps a fixed set of fields and drops the rest; type, priority, and status values outside its tables stop the import with the allowed set printed. Items carry `source` (`jira:SN-101`) so a re-import with `--merge` updates in place and never duplicates.

## Onsite-only live check

Not done in this repository: nothing here has been run against a real Jira, GitLab, or Azure DevOps host.
With an approved host and a read-only PAT in the customer environment, verify and record:

- [ ] Outbound HTTPS to the host is allowed and the certificate chain validates (set `REST_CA_BUNDLE` for a private CA).
- [ ] `python integrations/rest_client.py --dry-run <vendor> ...` shows the intended URL with `<redacted>` for the token.
- [ ] The same command without `--dry-run` returns HTTP 200; a deliberately wrong token returns 401 and the error names no token value.
- [ ] Page walk: repeat with `startAt`/`page` until `total`/`X-Next-Page` says done; count equals the vendor UI count before any filter.
- [ ] Field names in the real response match what `tracker_import.py` reads (status, priority, type, dates); note any custom workflow states and extend the tables in that file deliberately.
- [ ] Import the real export with `tracker_import.py`, run `tracker_report.py`, and compare totals with the vendor UI.
- [ ] Azure DevOps: a saved query id from Boards > Queries works with `ado query`; ad-hoc WIQL is not used.
- [ ] Token scope is read-only, expiry is set, and the shell history contains no token value.

## Boundary reminder

None of the vendor services above are inside your Devin FedRAMP authorization boundary by default.
Ask your administrator before sending data to them, and treat lanes 2-4 as "approved integration
required". Lane 1 needs no approval.
