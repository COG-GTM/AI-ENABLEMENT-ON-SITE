# Environment Readiness Checklist

Complete this checklist before opening any demonstration material in Devin.

## Deployment and identity

- [ ] The approved Federal application and tenant have been identified.
- [ ] The operator is authenticated with the approved identity and least-privilege role.
- [ ] The Desktop and CLI versions are approved for use.
- [ ] Organization-level permissions and policy controls are active.
- [ ] The operator knows how to stop the agent and revoke an approval.

## Workspace and data

- [ ] The repository is a clean, standalone workspace.
- [ ] No unrelated directory has been added to the workspace.
- [ ] All demo inputs are synthetic or explicitly approved and sanitized.
- [ ] The workspace contains no secrets, private keys, regulated data, production data, or identifying artifacts.
- [ ] Git status and the expected branch are known.

## Tools

- [ ] Required runtimes and tools are already installed from approved sources.
- [ ] Build, test, lint, and formatting commands are documented and tested.
- [ ] No package installation is required during the primary demo.
- [ ] Commands do not need elevated privileges.
- [ ] A read-only scenario is available if write access is not approved.

## Network and integrations

- [ ] Required network destinations are documented and approved.
- [ ] Each MCP server, plugin, API, issue tracker, and source-control integration is separately approved.
- [ ] The demo does not depend on an unapproved commercial tenant or public service.
- [ ] A no-network fallback is ready.

## Evidence and recovery

- [ ] Expected output and success evidence are defined.
- [ ] The starting commit or restore point is known.
- [ ] The fallback recording, screenshots, or static diff has been sanitized and approved.
- [ ] Stop conditions and escalation roles are understood.

If any boundary item is unknown, pause that portion of the demonstration rather than infer approval.
