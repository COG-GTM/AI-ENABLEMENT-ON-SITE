---
name: plan-to-tracker
description: Convert spec-driven task rows into Jira issue payloads with dry-run review first.
argument-hint: "[specs/<nnn>-<slug>/tasks.md] [--project KEY]"
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

Convert a `/spec-driven` task list from `$ARGUMENTS` into Jira v2 issue payloads. External writes are
opt-in and require an explicit `--apply`, `JIRA_URL`, `JIRA_TOKEN`, and typed confirmation unless
`--yes` was explicitly selected.

## Procedure

1. Generate a dry-run payload first:

   ```bash
   python tools/plan_to_tracker.py specs/<nnn>-<slug>/tasks.md --project <PROJECT>
   ```

2. Show the payload and CSV (if requested) to the developer. Confirm project, issue type, summaries,
   descriptions, labels, and suggested `feature/<KEY-placeholder>-<slug>` branch names.
3. Assign each created issue to its owner in Jira. The payload intentionally leaves assignee empty
   and states that the owner sets it in Jira.
4. Only after explicit approval, set `JIRA_URL` and `JIRA_TOKEN` in the shell and run with `--apply`.
   The command asks the developer to type `yes`; use `--yes` only when explicitly requested.
5. Create a separate branch per issue using the real issue key, and reference that key in each
   developer-reviewed conventional commit message.
6. Use `/connect-tools` for credential and Jira access setup. Never put token values in a file or
   chat. Start with `--check` to exercise the deterministic local example without network access.
7. Applied state is tied to a normalized Jira base URL. Use a new `--out` or reconcile before applying
   that state to a different Jira instance; dry runs preserve the stored URL.
8. Each created issue keeps a hash of its posted payload. If its task changes later, the tool marks it
   stale and reports the task and Jira key in stdout, Markdown, and CSV notes. It never re-posts or
   updates keyed issues; update stale issues in Jira by hand.
