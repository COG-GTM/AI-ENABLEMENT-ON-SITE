---
name: mcp-server
description: Stand up or register an MCP server by hand in Devin Local - run the offline reference server, add a server entry to .devin/mcp_config.json, or write a new read-only tool - without the marketplace.
argument-hint: "[run-reference | add <name> | new-tool <what it should return>]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(.devin/mcp_config.json)
    - Write(integrations/**)
triggers:
  - user
  - model
---

# MCP server by hand

User request: $ARGUMENTS

An MCP server is a process that speaks JSON-RPC 2.0 over stdin/stdout and answers three methods: "initialize", "tools/list", and "tools/call". That is all. The reference implementation is `integrations/reference-mcp/server.py` (about 160 lines, standard library only, no network).

## A. Run the reference server (offline, always works)

```bash
python integrations/reference-mcp/server.py < integrations/reference-mcp/handshake.jsonl
python -m unittest integrations/reference-mcp/test_server.py
```

The first command prints one JSON line per request: the handshake, the three tools, one requirement, and a power budget. Show the user; it demonstrates the whole protocol in five lines.

## B. Register a server in Devin Local

1. `.devin/mcp_config.json` is the project-scoped server list. It already registers the offline reference server. To add another, copy an entry from `integrations/mcp_config.example.json` into it.

2. Secrets stay in the environment. Config values use `${VAR}`; never a literal token.
3. Start a new Devin session so the server list is reloaded, then ask: "list the tools on the reference-system server".
4. If the desktop offers a CLI, `devin mcp list` shows registration status; it is optional, the file is the source of truth.

External servers (Jira Data Center, GitHub) are in the same example file. They need administrator approval, network reach, and their own runtime (see comments in each block). Remove blocks you are not using.

## C. Write a new read-only tool

1. Add an entry to `TOOLS` in `server.py` with a JSON Schema that uses `pattern`, `minimum`/`maximum`, and `additionalProperties: false`.
2. Add a `tool_<name>(args)` function that validates every argument again in code, reads only from the repository, and returns a string.
3. Register it in `HANDLERS`.
4. Add a case to `test_server.py`: a good call and a bad input that must return `isError: true`, not crash.
5. Run the tests and `python tools/check_repo.py`.

Rules: no write tools without explicit approval; no shelling out with user-supplied strings unvalidated; errors returned to the client are generic (no stack traces, paths, or secrets).

## Offline fallback

Sections A and C need nothing outside the repository. If this desktop build does not load the project MCP config, the same tools are callable directly: `python tools/tracker_report.py --json`, `python tools/what_if.py --imu imu-b`.
