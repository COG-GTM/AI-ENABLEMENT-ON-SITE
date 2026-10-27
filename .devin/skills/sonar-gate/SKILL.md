---
name: sonar-gate
description: Run a read-only SonarQube scan and gate the quality status and new-code issues.
argument-hint: "[project key] [--branch branch-name|--pull-request number]"
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

Scan and gate `$ARGUMENTS` before commit. Do not change SonarQube configuration, suppress an issue,
or write to the server from this workflow.

## Choose the approved scan lane

1. Confirm the SonarQube URL, project key, target branch or pull request, and that the developer
   approved network access. Do not ask for a token in chat; use the developer's approved
   `SONAR_URL` and `SONAR_TOKEN` environment configuration.
2. Use the team's approved `sonar-scanner` CLI when it is installed and configured:

   ```bash
   sonar-scanner -Dsonar.qualitygate.wait=true
   ```

3. Alternatively, use a SonarQube MCP server only if the administrator registered and approved one.
   See `/mcp-server` and `integrations/mcp-hosting.md`; do not install or name an unverified server.
4. Read the gate and new-code issues with `tools/sonar_gate.py`, using the project key and matching
   branch or pull request. Review the report before committing.
5. For offline practice, run `python integrations/fake_server.py` and use its SonarQube-shaped
   read-only routes, or run `python tools/sonar_gate.py --check`.

The tool reads status and issue data only. A `NONE` result means the gate was not computed and is an
error, not a passing result. A `WARN` may be treated as non-blocking unless the team selects
`--fail-on-warn`.

## Dependency vulnerability hand-off

For a P0 or P1 dependency CVE, do not silently suppress the finding. Create a tracker hand-off with
the affected dependency, CVE identifier, severity, evidence, and owner. The owner fixes it on a
feature branch, runs the relevant tests and scanner again, and reviews the new gate before merge.
