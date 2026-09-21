# Project Rules

- Keep all content reusable, customer-neutral, and free of organization, program, project, participant, and location identifiers.
- Use only the approved Federal deployment of Devin and separately approved integrations; never claim an unverified service is inside the FedRAMP authorization boundary.
- Use synthetic or explicitly approved sanitized data. Never add secrets, credentials, tokens, private keys, PII, PHI, PCI data, CUI, classified data, export-controlled data, production data, or proprietary customer artifacts.
- Never copy files from outside this repository without explicit approval and a data-handling review.
- Use least privilege. Start in Plan or Normal mode, keep tool access narrow, and request approval before network access, external integrations, writes outside the repository, or real-world side effects.
- Do not perform destructive operations, production changes, credential changes, deployments, purchases, messages, or external publication as part of a demonstration.
- Keep examples generic and replace identifying details with clearly synthetic placeholders.
- Prefer small, reviewable changes and verify the result before declaring completion.
- Before committing, inspect the complete staged diff for identifiers, sensitive data, secrets, generated artifacts, and unsupported compliance claims.
- Keep this file concise; put detailed procedures in `docs/` and reusable task material in `templates/` or `use-cases/`.
