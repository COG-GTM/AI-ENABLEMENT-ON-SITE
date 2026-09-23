# Vendor CLI recipes (read-only)

Use these when the CLI is already installed and approved on the laptop. Devin runs them in the
terminal like any other command; you approve each one. Check first: `which glab gh az acli`.

| Vendor | CLI | Login (token, no browser) | Login (browser / SSO) |
| --- | --- | --- | --- |
| GitLab | `glab` | `glab auth login --hostname gitlab.example.internal --token "$GITLAB_TOKEN"` | `glab auth login` (interactive) |
| GitHub / GHES | `gh` | `echo "$GITHUB_TOKEN" \| gh auth login --hostname ghes.example.internal --with-token` | `gh auth login --web` |
| Azure DevOps | `az devops` | `export AZURE_DEVOPS_EXT_PAT="$ADO_TOKEN"` then `az devops configure --defaults organization=$ADO_ORG project=<p>` | `az login` |
| Jira / Confluence Cloud | `acli` (Atlassian CLI); **Cloud only**, do not point it at Data Center | `acli jira auth login --site <site>.atlassian.net --email "$JIRA_EMAIL" --token` (prompts) | `acli jira auth login --web` |
| Jira Data Center (on-prem) | `jira-cli` (open source, tested here against the offline fake); Appfire Jira CLI (commercial, needs an admin-installed connector app); `go-jira` (older). Full guide: `jira-on-prem.md` | `export JIRA_API_TOKEN="$JIRA_TOKEN" JIRA_AUTH_TYPE=bearer` then `jira init --installation local --server "$JIRA_BASE" --login <username> --auth-type bearer --project SN --board none` | none for PATs; `--auth-type mtls` for client certificates |

## GitLab (`glab`)

```bash
glab issue list --repo group/project --per-page 20
glab issue view 42 --repo group/project
glab mr list --repo group/project --state opened
glab api "projects/:id/issues_statistics"
```

## GitHub (`gh`)

```bash
gh issue list --repo owner/repo --state open --limit 20 --json number,title,labels
gh pr list --repo owner/repo --state open
gh api repos/owner/repo/issues --paginate --jq '.[].title'
```

## Azure DevOps (`az devops`)

```bash
az boards query --wiql "SELECT [System.Id],[System.Title],[System.State] FROM WorkItems WHERE [System.State] = 'Active'" -o table
az boards work-item show --id 1234 -o json
az repos pr list --status active -o table
```

## Jira Cloud (`acli`)

```bash
acli jira workitem search --jql "project = SN AND status = Open" --limit 20
acli jira workitem view SN-42
```

## Jira Data Center (`jira-cli`)

One Go binary from github.com/ankitpokhrel/jira-cli, nothing installed in Jira. PAT in `JIRA_API_TOKEN`,
`JIRA_AUTH_TYPE=bearer`; `init` records server, login, and project in `~/.config/.jira/.config.yml`
(never the token). Verified against `fake_server.py` with v1.7.0; see `jira-on-prem.md` for the
step-by-step, the six GETs `init` makes, and the transcript.

```bash
jira me
jira serverinfo
jira issue list --plain
jira issue list -s "In Progress" --plain
jira issue list -tBug --plain
jira issue view SN-103 --plain
jira issue list -s Done --csv > outputs/jira-done.csv       # --raw is jira-cli's reshaped JSON (issueType), not Jira's; for tracker_import.py use rest_client.py
```

Read-only means: no `issue create|edit|move|assign|delete`, no `comment add`, no `sprint add`.
Appfire Jira CLI (commercial) and `go-jira` are described in `jira-on-prem.md`; neither was run here.

## Patterns worth copying

- Ask for JSON (`--json`, `-o json`) and let Devin reshape it into `example-system/tracker.json` form,
  then reuse `tools/tracker_report.py` and `/exec-deck` unchanged.
- Never pass tokens as literal arguments in a chat; use env vars set in the terminal.
- If a CLI is missing and cannot be installed, drop to `curl-recipes.md`; the API is the same.
