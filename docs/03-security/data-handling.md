# Data Handling

## Repository policy

Only reusable guidance and synthetic demonstration assets belong in this repository.

| Data type | Repository | Agent context | Notes |
| --- | --- | --- | --- |
| Purpose-built synthetic material | Allowed after review | Allowed within task scope | Preferred |
| Approved public material | Allowed after license and content review | Allowed within task scope | Preserve attribution when required |
| Sanitized internal material | Do not store here | Only with explicit approval | Prefer recreating synthetically |
| Credentials or secrets | Prohibited | Prohibited | Use approved secret handling outside prompts and Git |
| PII, PHI, PCI, CUI, classified, export-controlled, or production data | Prohibited | Prohibited for this kit | Stop and use synthetic material |
| Customer-identifying or proprietary artifacts | Prohibited | Prohibited for this kit | Do not copy from an engagement |

## Minimum necessary context

- Add only the files required for the current task.
- Avoid broad home, desktop, download, mail, cloud-drive, or multi-repository workspaces.
- Do not paste terminal history, environment dumps, or full logs.
- Redact by replacement, not by visual overlay.
- Review generated output because a model may reproduce sensitive input.

## Git permanence

Assume committed content remains recoverable from history, forks, caches, and audit systems. If prohibited data may have been committed, stop and follow the approved incident process rather than attempting an uncoordinated cleanup.
