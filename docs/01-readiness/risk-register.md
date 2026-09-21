# Reusable Risk Register

Do not add identifying details. Use role-based owners and generic descriptions.

| ID | Risk | Signal | Preventive control | Response | Owner role | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-001 | Unapproved data enters context | Paste, attachment, or broad workspace request | Synthetic data and scoped workspace | Stop, discard context, follow incident process | Security reviewer | Open |
| R-002 | Unapproved integration is invoked | Network or MCP approval prompt | Preflight allowlist and default deny | Decline and use offline fallback | Operator | Open |
| R-003 | Demo changes production | Production remote, credentials, or deployment command | Isolated demo repository and no production credentials | Stop and revoke access | Technical reviewer | Open |
| R-004 | Agent proposes destructive action | Delete, force, reset, or privileged command | Plan review and permission deny rules | Reject and choose reversible method | Operator | Open |
| R-005 | Live demo fails | Tool, network, or dependency error | Rehearsal and deterministic assets | Use tested fallback and explain honestly | Facilitator | Open |
| R-006 | Compliance claim is overstated | Boundary or feature statement lacks evidence | Use approved source material and qualify scope | Correct the statement and record follow-up | Security reviewer | Open |
| R-007 | Notes identify participants or systems | Names or unique details appear in notes | Role-based, sanitized note template | Remove before commit and review history | Note taker | Open |
