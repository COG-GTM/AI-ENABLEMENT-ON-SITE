---
name: mcp-server
description: Stand up, register, or decide how to host an MCP server in Devin Local - run the offline reference server, write a new read-only tool, add a server entry to .devin/mcp_config.json, or choose between laptop, shared, team-hosted, and vendor-hosted models by asking about the environment first - without the marketplace.
argument-hint: "[run-reference | new-tool <what it should return> | add <name> | host]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(.devin/mcp_config.json)
    - Write(.devin/mcp_config.local.json)
    - Write(integrations/**)
triggers:
  - user
  - model
---

# MCP server by hand

User request: $ARGUMENTS

An MCP server is a process that speaks JSON-RPC 2.0 and answers three methods: "initialize", "tools/list", and "tools/call". That is all. Over stdin/stdout it is a local process Devin starts; over HTTPS it is a server someone hosts. The reference implementation is `integrations/reference-mcp/server.py` (about 160 lines, standard library only, stdin/stdout, no network).

Pick the section that matches the request. `run-reference` and `new-tool` need nothing outside this repository. `add` and `host` change config and start with the questions in section D; do not skip them.

## A. Run the reference server (offline, always works)

```bash
python integrations/reference-mcp/server.py < integrations/reference-mcp/handshake.jsonl
python -m unittest integrations/reference-mcp/test_server.py
```

The first command prints one JSON line per request: the handshake, the three tools, one requirement, and a power budget. Show the user; it demonstrates the whole protocol in five lines.

## B. Write a new read-only tool

1. Add an entry to `TOOLS` in `server.py` with a JSON Schema that uses `pattern`, `minimum`/`maximum`, and `additionalProperties: false`.
2. Add a `tool_<name>(args)` function that validates every argument again in code, reads only from the repository, and returns a string.
3. Register it in `HANDLERS`.
4. Add a case to `test_server.py`: a good call and a bad input that must return `isError: true`, not crash.
5. Run the tests and `python tools/check_repo.py`.

Rules: no write tools without explicit approval; no shelling out with user-supplied strings unvalidated; errors returned to the client are generic (no stack traces, paths, or secrets).

## C. Register a server (`add <name>`)

Only after section D has produced a model and a file.

1. Copy the matching block from `integrations/mcp_config.example.json` into the file section D chose (`.devin/mcp_config.json` for everyone who clones; `.devin/mcp_config.local.json` for this user only; the user-level file for every project on the machine). Keep the `_comment` line; it says what runtime or host the entry expects.
2. Secrets never appear in the file. Use `${env:VAR}` (shell) or `${file:~/path}` (file). Confirm the variable exists with `env | grep -c VAR` (prints a count, not the value). Never ask the user to paste a token into the chat.
3. Local servers (`command`): confirm the runtime is present (`command -v python3 node docker github-mcp-server lvkit`) before writing the entry. For Jira Data Center the ready-made entry is `jira-readonly` (the self-hosted `COG-GTM/jira-mcp` connector, Docker form); `integrations/jira-on-prem.md` option 6 explains what it enforces, how it was tested, and the no-Docker form (`python3 -m connector.server` from that repo's directory, never the script by path). Remote servers (`url`): confirm the host is approved and reachable (`curl -sI https://host/mcp` from the user's shell, only after approval).
4. Show the diff. Run `python tools/doctor.py`; it validates every entry in all three files (`.devin/mcp_config.json`, `.devin/mcp_config.local.json`, and the user file when they exist): command on PATH, script exists, `url` is `https://`, `env`/`headers` values are strings, no literal token, and a same-named entry in a higher-precedence file repeats every key of the one it overrides.
5. Tell the user to start a new Devin session so the server list reloads, then ask: "list the tools on the <name> server". If the desktop offers a CLI, `devin mcp list` shows registration status; the file is the source of truth. Remote servers that answer `401` need `devin mcp login <name>` (browser sign-in), not a config change.

## D. Ask about the environment first (`host`, or any mention of shared, central, team, remote, or vendor MCP)

Ask these one at a time; stop as soon as the answers settle on a model. Do not write any config until they are answered. Never assume network reach, approval, or a credential type.

| # | Ask | Answer -> model |
| --- | --- | --- |
| 1 | Who else needs these tools? | just me -> **A laptop**; my team, same repo -> **B shared entry**; several teams, or "we need one audit log" -> **C team-hosted**; a vendor already runs it -> **D vendor-hosted** |
| 2 | Can this laptop reach the host? (offline / internal host over HTTPS / internet) | offline or unknown -> only A or B; internal host -> C possible; internet -> D possible |
| 3 | Has an administrator approved that host and its data path? | yes -> continue; no or unknown -> write the entry into `.devin/mcp_config.local.json` with `"disabled": true`, or use the offline stand-in `integrations/fake_server.py` |
| 4 | How will you log in? (token in your shell / single sign-on / don't know) | token -> `${env:VAR}` in `env` or `headers`; SSO -> no header, `devin mcp login <name>` after registering; don't know -> stop and name what the administrator must provide |
| 5 | Which file? (just me / everyone who clones / every project on this machine) | local override / project / user |
| 6 | Read-only? | yes -> proceed; no -> list the write tools by name and require explicit approval for each before enabling |

Then:

- **A or B**: go to section C. For B, the project entry carries no secret and the user's token sits in their shell or in the local override.
- **C**: Devin's side is one `url` entry (section C). The server itself is the platform team's work. Print the "Before you take model C to the platform or security team" checklist from `integrations/mcp-hosting.md`, filled in with the answers above, and stop there; nothing in this repository stands up an HTTP server, proxy, or certificate.
- **D**: confirm the vendor endpoint is approved and whether it is inside the user's authorization boundary (do not claim it is). Then section C with `devin mcp login`.

If the user cannot answer 2, 3, or 4, default to model A against the offline reference server and say exactly which answer is missing.

The models, their trade-offs, the file locations, and the nuances (permissions namespace `mcp__<server>__*`, `url` vs `serverUrl`, `401` means log in, Windows paths) are in `integrations/mcp-hosting.md`. Point the user there rather than repeating it.

## Offline fallback

Sections A and B need nothing outside the repository. If this desktop build does not load the project MCP config, the same tools are callable directly: `python tools/tracker_report.py --json`, `python tools/what_if.py --imu imu-b`.
