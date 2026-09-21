# FedRAMP Boundary

## Principle

FedRAMP authorization applies to a defined service offering and authorization boundary. It does not automatically extend to every deployment, endpoint, model, plugin, MCP server, repository host, identity provider, package registry, or external integration.

## Required confirmation

Before a session, the security reviewer must confirm through approved internal sources:

- The specific Federal Devin deployment and tenant
- The approved identity and access path
- The installed Desktop and CLI distribution
- Organization-level policy controls
- Data types permitted in the service
- Approved network paths and destinations
- Separately approved integrations and repositories
- Logging, retention, and incident procedures

Do not place tenant identifiers, endpoints, authorization artifacts, or account details in this repository.

## Default decision

If a component's status is unknown, treat it as outside the approved boundary and remove it from the demonstration. Never use an unapproved commercial account as a fallback.

## Claims

State only facts supported by current, approved documentation. Qualify each statement to the specific service and boundary. This repository is planning material and must not be cited as authorization evidence.
