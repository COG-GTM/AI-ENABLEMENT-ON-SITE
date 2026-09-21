# Access and Integrations

Use this matrix to record generic approval status. Do not record account identifiers, endpoint hostnames, tokens, or customer-specific configuration.

| Capability | Needed | Approval owner role | Minimum access | Status | Fallback |
| --- | --- | --- | --- | --- | --- |
| Federal Devin tenant | Yes | Security reviewer | Standard operator | Verify | Static walkthrough |
| Source repository | Yes | Repository administrator | Read; scoped write if needed | Verify | Local synthetic repository |
| Package registry | Optional | Platform administrator | Read-only | Verify | Preinstalled dependencies |
| Issue tracker | Optional | Application owner | Read-only demo project | Verify | Local synthetic issue |
| MCP server | Optional | Security reviewer | Tool-specific | Verify | Disable integration |
| External web access | Optional | Security reviewer | Approved destinations only | Verify | Offline documentation |
| Build infrastructure | Optional | Platform administrator | Read-only logs or isolated runner | Verify | Local deterministic build |

## Decision rule

Unknown, inherited, or implied access is not approval. Remove the dependency from the run of show until the appropriate owner confirms it.
