---
name: tour
description: First-run tour of this repository - check the laptop is ready, run every test, open the example deck, and explain in five lines what the user can do next.
argument-hint: "[nothing, or a topic you care about]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(outputs/**)
triggers:
  - user
  - model
---

Give a first-time user a working tour in under two minutes. Request: `$ARGUMENTS`.
Everything below runs offline. If a command is refused or fails, say so plainly and continue.

## Steps

1. Readiness: `python tools/doctor.py`. Read the table to the user in one line
   (Python version, how many skills were found, MCP config OK or not, C compiler present or absent, no network needed).
2. Proof: `python tools/check_repo.py`. Report the final `OK:` line or the first problem.
3. Something to look at: `python tools/build_deck.py templates/deck-outline-example.json outputs/example-deck.html`,
   then open `outputs/example-deck.html` in the preview. Mention arrow keys and `P` to print.
4. What is here, in five lines, from `README.md` "Where things live": the synthetic sensor node,
   the tools, the skills, the integrations folder, where outputs land.
5. Next step: point at `WORKFLOWS.md` and suggest the first pipeline
   (`/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN`, then `/exec-deck`).
   If the user named a topic in `$ARGUMENTS`, suggest the matching skill from `AGENTS.md` instead.

## Rules

- Do not modify files outside `outputs/`.
- Do not claim anything the commands did not print. If `check_repo.py` reports problems, show them.
- Keep the whole tour to about ten lines of chat plus the deck preview.
