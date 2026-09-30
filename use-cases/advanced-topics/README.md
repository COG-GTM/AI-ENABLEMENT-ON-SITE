# Use case (discussion only): advanced topics to scope with engineering managers

**Status: discussion material, not build-ready exercises.** These questions came up alongside the migration lanes:
choosing models and sub-agents to control token cost, writing `AGENTS.md` without over-constraining the agent,
running Devin Desktop on Windows, working in a remote-container workspace, and knowing which recommended tools are
approved for the environment. Each section states what this repository already shows, what the product documentation
says (with the page cited), and what is still to be scoped.

## 1. Model and sub-agent choice to reduce token cost

What this repository does about cost is structural and works with any model: bounded packs per unit, leaf-first order,
files instead of transcripts, a dry run before an agent is involved, and a manifest with token estimates before anything
runs (`use-cases/reusable-pipeline/README.md`). Do that first; it is the largest saving and it is repeatable.

Model selection is a product setting, not something a repository controls. Devin's documentation describes:

- `/model opus`, `/model sonnet`, `/model codex` in the CLI, and `/model` to open a selector
  (https://docs.devin.ai/cli/models#setting-the-model).
- A default model in `~/.config/devin/config.json` (Windows: `%APPDATA%\devin\config.json`).
- Devin Fusion, which pairs a lead model, an effort level, and a sidekick model
  (https://docs.devin.ai/desktop/fusion#choosing-a-pairing).
- Availability depends on plan, team restrictions, and model allowlists set by the administrator.

To scope: which models are permitted in the environment; whether a cheaper model runs the scan-and-pack review while a
stronger one does the per-unit migration; and how the team measures cost per unit from the pipeline's manifest.

## 2. Writing `AGENTS.md` without over-constraining the agent

This repository's `AGENTS.md` is a worked example: under 40 lines, a routing table (what the user says -> which skill), a
short rules list, and a pointer to `README.md` when nothing matches. Procedures live in skills, one file each, so the
agent reads the long text only for the task at hand. Rules of thumb that held here:

- Route, do not instruct: the table names skills; the skills hold steps.
- State constraints that protect people and data (customer-neutral, synthetic data, ask before network or writes outside
  the repository, no destructive side effects) and leave method to the skill.
- Keep one verification command the agent must run before declaring done (`python tools/check_repo.py`).
- Enforce the file's own rules with a tool (`tools/check_repo.py` checks routing, links, forbidden terms, skill cap).

To scope: which of the team's existing standards (coding standard, review checklist, ticket conventions) belong in
`AGENTS.md` versus a skill versus CI.

## 3. Devin Desktop on Windows

The repository's tools are standard-library Python and run on Windows; `integrations/mcp-hosting.md` already gives
Windows paths for the MCP configuration. Documentation notes: the default model configuration lives in
`%APPDATA%\devin\config.json`; SSH password prompts may open `cmd.exe` windows
(https://docs.devin.ai/desktop/advanced#ssh-support). WSL 2 is one way to get a Linux toolchain (`gcc`, `make`) for the C
lanes; the pure-Python lanes do not need it.

To scope: whether the target laptops have a C compiler, whether `lvkit` can be installed from the offline wheel, and
which shell the team uses (the commands in this repository are shown for a POSIX shell; they run unchanged in PowerShell
except for line continuations).

## 4. Remote-container workspace

Documentation states Devin Desktop supports dev containers on Mac, Windows, and Linux, locally and over SSH, given
Docker and a `devcontainer.json` (`Dev Containers: Open Folder in Container`, `Reopen in Container`,
`Attach to Running Container`; https://docs.devin.ai/desktop/advanced#dev-containers). Its SSH support requires OpenSSH
and Linux-based remote hosts, and the standard Microsoft Remote-SSH extensions must not be installed alongside it
(https://docs.devin.ai/desktop/advanced#ssh-support). Worktree sessions are described at
https://docs.devin.ai/desktop/devin-local#worktree-sessions.

This repository does not ship a `devcontainer.json`; one that installs Python 3.10+, `gcc`, `make`, and the `lvkit`
wheel would let the whole golden path run inside the container. To scope: where the container image is built and
approved, and whether the source tree lives in the container or on a mounted volume.

## 5. Tool approval status

`integrations/tool-approval-status.md` lists every tool, install, download, and service this repository mentions, with a
category (Authorized, In Process, Not on Marketplace, Not applicable, Unknown), the evidence URL, and the date checked.
FedRAMP authorizes cloud service offerings; desktop software, open-source libraries, and this repository's own scripts
fall under the agency's software-approval process. Never claim a service is inside a boundary without the administrator's
confirmation (`AGENTS.md`, `SECURITY.md`).

## Skills and files

`AGENTS.md`, `tools/check_repo.py`, `integrations/mcp-hosting.md`, `integrations/tool-approval-status.md`, `SECURITY.md`,
`use-cases/reusable-pipeline/README.md`.
