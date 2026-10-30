# Team repository instructions

Use these local guardrails together with GitLab branch protection configured by a maintainer.

## Development rules

- Work on a feature or development branch; never commit or push to `main`.
- Require at least 80% coverage on changed, instrumented lines; the team may raise the threshold to 85%.
- Run `/sonar-gate` before committing application changes.
- Use `/spec-driven` followed by `/tdd` for feature work.
- Devin may draft conventional commit messages; the developer reviews and approves every message.
- Ask before any network access or external integration.
- Adapt the runner commands and scanner configuration to this team's approved Angular setup.
