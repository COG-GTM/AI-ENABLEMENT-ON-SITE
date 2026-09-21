# Vendor CLI recipes (read-only)

Use these when the CLI is already installed and approved on the laptop. Devin runs them in the
terminal like any other command; you approve each one. Check first: `which glab gh az acli`.

| Vendor | CLI | Login (token, no browser) | Login (browser / SSO) |
| --- | --- | --- | --- |
| GitLab | `glab` | `glab auth login --hostname gitlab.example.internal --token "$GITLAB_TOKEN"` | `glab auth login` (interactive) |
| GitHub / GHES | `gh` | `echo "$GITHUB_TOKEN" \| gh auth login --hostname ghes.example.internal --with-token` | `gh auth login --web` |
| Azure DevOps | `az devops` | `export AZURE_DEVOPS_EXT_PAT="$ADO_TOKEN"` then `az devops configure --defaults organization=$ADO_ORG project=<p>` | `az login` |
| Jira / Confluence Cloud | `acli` (Atlassian CLI) | `acli jira auth login --site <site>.atlassian.net --email "$JIRA_EMAIL" --token` (prompts) | `acli jira auth login --web` |
| Jira Data Center | none official | use `curl-recipes.md` | n/a |

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

## Patterns worth copying

- Ask for JSON (`--json`, `-o json`) and let Devin reshape it into `example-system/tracker.json` form,
  then reuse `tools/tracker_report.py` and `/exec-deck` unchanged.
- Never pass tokens as literal arguments in a chat; use env vars set in the terminal.
- If a CLI is missing and cannot be installed, drop to `curl-recipes.md`; the API is the same.
