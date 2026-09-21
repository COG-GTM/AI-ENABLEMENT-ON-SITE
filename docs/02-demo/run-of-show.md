# Run of Show

Build the final flow from the modules below. Remove any module whose boundary or fallback is not ready.

| Module | Operator action | Human review point | Evidence | Fallback |
| --- | --- | --- | --- | --- |
| Boundary | Show rules and permissions | Security reviewer confirms scope | Completed checklist | Static policy walkthrough |
| Understand | Ask for a focused architecture or code-path explanation | Reviewer checks citations against files | Referenced file map | Prepared architecture notes |
| Plan | Request a plan for a synthetic task | Reviewer edits scope and constraints | Approved plan | Prepared plan |
| Change | Allow a small implementation or documentation edit | Reviewer approves each material action | Focused diff | Prepared patch |
| Verify | Run existing tests or deterministic checks | Reviewer interprets failures and coverage | Command output | Recorded output |
| Review | Ask Devin to self-review the diff and edge cases | Reviewer validates findings independently | Review notes | Prepared checklist |
| Discover | Complete a use-case plan from a generic workflow | Participants score value and feasibility | Sanitized scorecard | Printed template |
| Close | Review decisions and actions | Owners accept role-based actions | Sanitized notes | Verbal recap |

## Narration pattern

For every module, state:

1. The outcome
2. The context being provided
3. The permissions being considered
4. The human decision point
5. The verification evidence
6. The stop or fallback condition
