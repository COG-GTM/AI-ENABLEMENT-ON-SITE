# Connecting Devin to your tools (Jira, GitLab, Confluence, GitHub, Azure DevOps)

Four ways to reach an external system, cheapest first. Start at the top; move down only when you
need to and your administrator has approved it. Everything here is read-only by default.

| Lane | What it is | Auth | Needs network | Needs install | Use when |
| --- | --- | --- | --- | --- | --- |
| 1. Offline | Work from files already in the repository (`example-system/tracker.json`, exported CSV/JSON) | none | no | nothing | Always works. Default for demonstrations. |
| 2. REST / curl | Devin calls the vendor HTTP API with `curl` or `rest_client.py` | PAT or API token in an env var | yes, to the vendor host | `curl` (present) or Python 3 | You have a token and want the fewest moving parts. |
| 3. Vendor CLI | `glab`, `gh`, `az devops`, `acli` run by Devin | the CLI's own login (token or browser) | yes | the CLI binary | The CLI is already installed and approved on the laptop. |
| 4. MCP server | A local process Devin talks to over stdio; tools show up in Devin | whatever the server uses (usually a PAT/env var) | usually yes | a runtime (Python/Node/Go) or a binary | You want the tools available in every session without re-explaining the API. |

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
| OAuth (any vendor) | browser sign-in through your IdP | handled by the client | admin enables the app | Needed for vendor-hosted MCP servers. Requires admin approval; not covered here beyond that. |

Least privilege: read scopes only, one token per tool, short expiry, never paste a token into a chat
or a file. Set it in the shell for the session: `export JIRA_TOKEN=...` (Windows: `$env:JIRA_TOKEN="..."`).

## Files in this folder

| File | Lane | What it does |
| --- | --- | --- |
| `curl-recipes.md` | 2 | Copy-paste read-only `curl` calls for each vendor, env vars only. |
| `rest_client.py` | 2 | Standard-library Python client: `python integrations/rest_client.py jira search "project = SN"`. `--dry-run` prints the request without sending. |
| `cli-recipes.md` | 3 | Read-only `glab`, `gh`, `az devops`, `acli` commands and how they log in. |
| `test_rest_client.py` | 2 | Offline tests: every command dry-runs, tokens are redacted, bad input is refused. |
| `mcp_config.example.json` | 4 | Entries to copy into `.devin/mcp_config.json`: the local reference server plus optional vendor servers (delete what you do not use). |
| `reference-mcp/server.py` | 4 | A complete MCP server in one file, no dependencies, exposing three read-only tools over `example-system/`. Already registered in `.devin/mcp_config.json`. |
| `reference-mcp/handshake.jsonl`, `reference-mcp/test_server.py` | 4 | Five-line protocol walkthrough and the tests that drive the server over a real pipe. |

## Boundary reminder

None of the vendor services above are inside your Devin FedRAMP authorization boundary by default.
Ask your administrator before sending data to them, and treat lanes 2-4 as "approved integration
required". Lane 1 needs no approval.
