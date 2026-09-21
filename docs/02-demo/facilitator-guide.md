# Devin Desktop and CLI Facilitator Guide

## Core message

Devin is most effective when the operator supplies a bounded objective, relevant context, explicit constraints, and a verification method. The demonstration should make human review visible at every consequential step.

## Desktop flow

1. Open only the approved synthetic repository.
2. Show `AGENTS.md` and explain persistent project rules.
3. Ask a narrow read-only question and require file references.
4. Switch to Plan mode for a change request.
5. Review and refine the plan before allowing edits.
6. Inspect proposed actions, the resulting diff, and validation output.
7. Ask for a self-review, then perform an independent human review.

Describe only controls and features verified in the approved installed version.

## CLI flow

1. Enter the repository and run `devin`.
2. Use `@` to attach only relevant files.
3. Use `/plan` before a multi-step or ambiguous change.
4. Use `/normal` for explicit approval of writes and commands.
5. Use `/accept-edits` only when workspace edits are understood and approved.
6. Use `/workspace` to verify the active workspace.
7. Use `/help` if a command or capability is uncertain.

Do not use unrestricted permission modes during the demonstration. Organization-level controls remain authoritative regardless of local mode.

## Prompt structure

Include:

- Desired outcome
- Relevant files or directory
- Constraints and prohibited actions
- Expected evidence
- Validation command
- Instruction to ask before expanding scope

## Failure handling

- Stop rather than improvising around a boundary or permission failure.
- Explain the observed error without inventing a cause.
- Use the prepared fallback.
- Record a sanitized follow-up question.
- Never weaken a security control to make a demonstration succeed.
