# Contributing

Keep it customer-neutral, synthetic, small, and runnable offline.

1. Branch from `main`.
2. Make the change. New procedures go in `.devin/skills/<name>/SKILL.md` and get one row in `AGENTS.md`; new numbers come from a tool, not from typing.
   - Frontmatter keys allowed: `name`, `description`, `argument-hint`, `model`, `allowed-tools`, `permissions`, `triggers`. Cap is 12 skills; merge before adding a thirteenth.
   - A skill that belongs in a chain also gets a stage row in `WORKFLOWS.md`: the prompt to paste and the file it leaves behind.
   - In `AGENTS.md`, `README.md`, `WORKFLOWS.md`, and `WALKTHROUGH.md`, write skill commands as code (`` `/exec-deck ...` `` or a fenced line starting with `/exec-deck`); the checker verifies each one exists. Write absolute paths in code with a second segment or trailing slash (`/usr/bin`, `/tmp/`) so they are not read as commands.
3. Run `python tools/check_repo.py`. It must print `OK`. CI runs the same command.
4. Read the whole diff for identifiers, secrets, and claims about compliance boundaries.
5. Open a pull request. Say what a first-time user can now do that they could not before.

Do not commit personal overrides (files matching `*.local.*`), tokens, or anything copied from an engagement.
