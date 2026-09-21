# Demonstration Data Guidance

## Preferred data

1. Purpose-built synthetic source code, tickets, logs, documents, and configuration
2. Public material whose license and use have been reviewed
3. Sanitized material approved for this exact demonstration and repository

Synthetic data should be realistic enough to exercise the workflow but must not encode real names, domains, identifiers, architecture, vulnerabilities, or operational details.

## Generation rules

- Use fictional organizations, systems, users, hosts, accounts, and addresses.
- Use reserved examples and obviously fake identifiers.
- Keep secrets as nonfunctional placeholders such as `REDACTED`.
- Avoid copying the shape of a sensitive production dataset when that shape is itself revealing.
- Remove file metadata from approved presentation assets.
- Verify that test fixtures cannot contact a real endpoint.

## Review

A second reviewer should inspect demo data, Git history, screenshots, and generated output before the session. When sanitization quality is uncertain, create new synthetic material instead.
