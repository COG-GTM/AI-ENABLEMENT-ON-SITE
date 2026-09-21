# Repository Readiness

## Required state

- Standalone repository with no nested repository or unrelated files
- Default branch and remote verified
- Clean working tree at the start of each write scenario
- Synthetic fixtures and deterministic validation commands
- No secrets in files, history, remotes, issues, or release artifacts
- No customer-identifying branch names, tags, commit messages, or metadata
- Small enough scope for participants to understand the expected change

## Recommended files

- `README.md` with setup and validation commands
- `AGENTS.md` with concise project rules
- Dependency manifests and lockfiles, if needed
- Automated tests or a deterministic verification script
- A known failing test for debugging scenarios
- A fallback patch or expected diff stored as sanitized material

## Review before use

1. Inspect the full file tree.
2. Inspect Git remotes, status, branches, tags, and recent log.
3. Search current content and history for secrets and identifying terms using approved tooling.
4. Run the documented validation commands without Devin.
5. Confirm that reset and cleanup steps are safe and approved.
6. Record the starting commit in the demo script without embedding environment-specific details.
