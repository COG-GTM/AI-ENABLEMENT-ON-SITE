---
name: connect-tools
description: Connect Devin to Jira, Confluence, GitLab, GitHub, or Azure DevOps from a Federal desktop using the right lane (REST/curl, vendor CLI, or MCP) and the right credential (PAT, API token, OAuth), read-only first.
argument-hint: "[tool] [--lane rest|cli|mcp] [--what 'issues in project X']"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(**)
triggers:
  - user
  - model
---

# Connect to an external tool

User request: $ARGUMENTS

Transport and authentication are separate decisions. Pick one from each column:

| Lane (transport) | Credential (auth) |
| --- | --- |
| REST via `curl` or `integrations/rest_client.py` | Jira/Confluence Data Center: PAT. Jira/Confluence Cloud: API token + email. GitLab: PAT. GitHub: fine-grained PAT. Azure DevOps: PAT. |
| Vendor CLI (`glab`, `gh`, `az devops`, `acli`) | Same tokens, or browser/SSO login where the vendor supports it. |
| MCP server (`/mcp-server`) | Local stdio server: token from environment. Vendor-hosted server: OAuth in the browser. |

Details and copy-paste commands: `integrations/README.md`, `integrations/curl-recipes.md`, `integrations/cli-recipes.md`.

## Steps

1. **Confirm approval and reach.** Ask whether the target host is approved for this desktop and whether outbound HTTPS to it is allowed. If not, stop and offer the practice path: `python integrations/fake_server.py` serves Jira-, GitLab-, and Azure DevOps-shaped read endpoints on `127.0.0.1` from synthetic fixtures, so every step below can be rehearsed with no network and no real token ("Prove it offline" in `integrations/README.md`).
2. **Confirm the credential exists.** Never ask the user to paste a token in chat. Ask them to export it in their shell (`export JIRA_TOKEN=...`) and tell you when done. Confirm with `env | grep -c JIRA_TOKEN` (prints a count, not the value).
3. **Choose the lane.**
   - No extra software allowed -> REST via `curl` or `python integrations/rest_client.py`.
   - Vendor CLI already installed (`command -v glab gh az acli`) -> CLI recipes.
   - Devin needs to call the tool repeatedly inside a session -> MCP (`/mcp-server`).
4. **Dry-run first.** `python integrations/rest_client.py --dry-run jira issue SN-42` prints the request with the token redacted. Review the URL and scope before sending anything.
5. **Read before write.** Every recipe here is read-only. Adding a write (create issue, post comment) needs explicit user approval each time and a scoped token.
6. **Reuse the repo tooling.** Save the JSON (or a CSV export) under `outputs/`, fetch every page first, then `python tools/tracker_import.py --from jira|gitlab|ado|csv --in outputs/<export> --out outputs/tracker.json` (add `--merge example-system/tracker.json` to update existing items by external id instead of duplicating). Run `python tools/tracker_report.py --file outputs/tracker.json --markdown` or feed `/exec-deck`, so external data flows through the same reports as the offline example. Unknown status or priority values stop the import and print the allowed set; extend the tables in `tracker_import.py` deliberately.
7. **Before the first live call, run the onsite checklist.** "Onsite-only live check" in `integrations/README.md` lists what to verify with a real PAT; none of it has been done in this repository.
8. **Leave nothing behind.** Do not save tokens to files in the repository. If a config file needs a value, reference `${VAR}` and let the environment supply it.

## Offline fallback

Everything above has an offline equivalent: `integrations/fake_server.py` stands in for the Jira, GitLab, and Azure DevOps APIs (same headers, pagination, and error codes; GET only), `tracker.json` for the tracker itself, `example-system/docs/` for Confluence, and `git log` for GitLab/GitHub. Say so when the network path is unavailable and continue with the offline data.
