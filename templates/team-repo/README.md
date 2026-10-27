# Team repository guardrail starter

This is a copyable example for an Angular application repository. It is not applied to this workflow
library. Review each placeholder and adapt commands to the team's approved toolchain before use.

## What's shared and what's local

| Path | Purpose | Usual treatment |
| --- | --- | --- |
| `AGENTS.md` | Repository-wide instructions and skill routing | Commit and share with the team |
| `.devin/rules/` | Branch, test, and Angular conventions | Commit and share with the team |
| `.devin/hooks.v1.json`, `hooks/block_main.py` | Local Devin CLI pre-command guard against operations on protected branches | Commit and share; each developer must confirm hook pickup on their build |
| `.gitlab-ci.yml` | Merge-request checks and approved image-build placeholder | Commit after adapting runner images, coverage commands, and registry |
| `.devcontainer/devcontainer.json` | Optional Node development container placeholder | Commit only if the team uses the approved container workflow |
| `global-skills/` | Examples for personal, cross-project skills | Examples only; install under the developer's global directory, never commit these into a team repo |
| `.devin/config.local.json`, `.devin/hooks.local.json` | Personal overrides or secrets if supported by the team's setup | Keep local and out of version control |

## Copying into an application repository

1. Review the team's applicable policy and approval for Node, npm, SonarQube, GitLab CI, and any
   container builder.
2. Copy the desired shared paths from this folder into the root of the Angular application repository.
   Keep the sample skill examples under `global-skills/` separate.
3. Edit the image, target-branch, test, and registry placeholders. Copy `tools/coverage_gate.py`
   from the workflow library into the application repo if the CI template will call it.
4. Open the application repo in Devin Desktop or Devin CLI. The configuration files instruct Devin;
   they do not grant access or change GitLab permissions.
5. Confirm branch protection for `main` is configured in GitLab by a maintainer. Devin uses the
   developer's own GitLab access; local instructions and hooks cannot create permissions or branch
   protection.

For Devin Desktop, place and open the files in the application repository folder, then confirm the
rules and skills are recognized using the commands below. For Devin CLI, copy the same committed
files into the repo root before starting a session. Hook pickup varies by installed build; confirm on
your build.

```bash
devin rules list
devin skills list
devin skills paths
```

Use a dedicated test branch to confirm the hook blocks a protected-branch commit and push. Do not use
a real protected branch for this test.

## Developer and platform notes

- `.devin/hooks.v1.json` and all rules are client-side guardrails, not GitLab access control.
- GitLab branch protection on `main` must be configured by a GitLab maintainer.
- Devin performs GitLab actions as the developer, using that developer's existing GitLab access.
- WSL details depend on the site's Windows image, Devin CLI build, and editor integration; confirm
  the workflow on your build.

## Global skills

The examples in `global-skills/` are personal skills. They belong in a developer's global skills
directory and are **not committed to a team application repository**. Verified Devin CLI locations:

- Linux and macOS: `~/.config/devin/skills/<skill-name>/SKILL.md`
- Windows: `%APPDATA%\devin\skills\<skill-name>\SKILL.md`

The `/my-commit-style` and `/my-review-checklist` examples are intentionally minimal.
