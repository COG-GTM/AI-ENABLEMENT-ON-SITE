# Security and Data Handling

## Scope

This repository contains reusable enablement material and synthetic demonstration assets. It must not be used as a store for customer data, production data, credentials, or regulated information.

## Required controls

- Use the organization-approved Federal deployment and approved identity provider.
- Confirm that each integration is approved and within its own documented boundary before enabling it.
- Grant only the repository, filesystem, command, and network access required for the current demonstration.
- Use synthetic data by default and minimize all context provided to an agent.
- Review proposed commands, diffs, logs, and generated output before sharing or committing them.
- Keep secrets in an approved secrets manager; never place them in prompts, files, screenshots, terminal history, or Git history.

## Prohibited repository content

- Customer, participant, program, site, or system identifiers
- Passwords, tokens, certificates, private keys, connection strings, or session data
- PII, PHI, PCI data, CUI, classified data, export-controlled data, or production records
- Proprietary source code, logs, tickets, architecture, screenshots, or documents copied from an engagement
- Unverified claims that a service or integration is FedRAMP authorized

## Reporting

Report a suspected exposure or vulnerability through the organization-approved private security channel. Do not place sensitive details in a public issue. If sensitive data may have entered Git history, stop work, notify repository administrators, and follow the approved incident process before resuming.
