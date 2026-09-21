# Contributing

Keep it customer-neutral, synthetic, small, and runnable offline.

1. Branch from `main`.
2. Make the change. New procedures go in `.devin/skills/<name>/SKILL.md` and get one row in `AGENTS.md`; new numbers come from a tool, not from typing.
3. Run `python tools/check_repo.py`. It must print `OK`.
4. Read the whole diff for identifiers, secrets, and claims about compliance boundaries.
5. Open a pull request. Say what a first-time user can now do that they could not before.

Do not commit personal overrides (files matching `*.local.*`), tokens, or anything copied from an engagement.
