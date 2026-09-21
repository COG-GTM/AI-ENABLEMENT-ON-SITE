# Devin CLI Demo Cheat Sheet

Use commands available in the approved installed version. Run `/help` when uncertain.

| Action | Command or interaction |
| --- | --- |
| Start an interactive session | `devin` |
| Start with an initial prompt | `devin -- "your bounded prompt"` |
| Ask without making changes | `/ask <question>` |
| Enter planning mode | `/plan` |
| Return to explicit-approval mode | `/normal` |
| Allow workspace edits while retaining command prompts | `/accept-edits` |
| Inspect active workspaces | `/workspace` |
| Attach a relevant file or directory | Type `@` and select the item |
| Show available commands | `/help` |
| Exit | `/exit` |

## Safe demonstration defaults

- Begin with a clean Git working tree.
- Use Plan or Normal mode.
- Keep the workspace limited to the synthetic repository.
- Review each requested permission.
- Do not enable unrestricted execution.
- End by reviewing `git diff`, validation output, and remaining risks.
