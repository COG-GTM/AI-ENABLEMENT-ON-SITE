# Hosting an MCP server: on your laptop, for your team, or from a vendor

An MCP server is a small program that gives Devin extra tools (read a requirement, query the
tracker, look inside a VI). "Hosting" is just the question of **where that program runs and who
looks after it**. There are four honest answers. This page helps you pick one, tells you what each
one needs, and lists the questions Devin will ask before it changes any config.

Everything in this repository so far uses model A. Models B and C are what a team or a platform
group sets up; model D is a vendor's server. `/mcp-server host` walks you through the choice.

## The four models in one picture

```
 A. On your laptop                     B. Shared definition, personal secret
 ┌──────────────────────────┐          ┌──────────────────────────┐   git   ┌──────────────┐
 │ Devin Desktop            │          │ Devin Desktop            │◄────────┤ team repo    │
 │  └─ starts ─► server.py  │          │  └─ starts ─► server     │         │ .devin/      │
 │      (stdin/stdout)      │          │      (stdin/stdout)      │         │ mcp_config   │
 │ .devin/mcp_config.json   │          │ + my token in            │         │ .json        │
 └──────────────────────────┘          │   mcp_config.local.json  │         └──────────────┘
  nothing leaves the machine           └──────────────────────────┘
                                        same as A, but the entry is versioned and
                                        every laptop gets the same one

 C. Team-hosted, on your network       D. Vendor-hosted, on the internet
 ┌──────────────┐  HTTPS  ┌─────────┐  ┌──────────────┐  HTTPS + OAuth  ┌─────────────────┐
 │ Devin Desktop├────────►│ reverse │  │ Devin Desktop├────────────────►│ vendor's MCP    │
 │ "url": ...   │         │ proxy + │  │ "url": ...   │  browser login  │ endpoint        │
 └──────────────┘         │ auth    │  └──────────────┘                 └─────────────────┘
 ┌──────────────┐         ├─────────┤   outside your boundary unless your
 │ Devin Desktop├────────►│ MCP     │   administrator says otherwise
 └──────────────┘         │ server  │
   many laptops,          ├─────────┤
   one server             │ Jira /  │
                          │ GitLab /│
                          │ files   │
                          └─────────┘
```

## Pick one

| | A. On your laptop | B. Shared definition | C. Team-hosted | D. Vendor-hosted |
| --- | --- | --- | --- | --- |
| Where the server runs | your machine, started by Devin | your machine, started by Devin | a server your platform team runs | the vendor's cloud |
| Who installs and updates it | you | whoever maintains the repo (the entry) + you (the runtime) | the platform team, once | the vendor |
| Where the credential lives | your shell or `mcp_config.local.json` | same; the shared file has no secret | a header from your shell, or SSO login in the browser | OAuth login in the browser |
| Network needed | none (unless the server itself calls out) | none | reach to one internal host over HTTPS | internet, through whatever your proxy allows |
| Who can see what was asked | only you (local logs) | only you | the team, if the server logs | the vendor |
| Fails when | your laptop lacks the runtime | someone changes the entry and your laptop lacks the runtime | the host is down or you are off-network | vendor outage or token expiry |
| Pick it when | you are learning, offline, or the data is on this disk | a team shares one repo and each person has their own token | many people need the same tools against one internal system, and the security team wants one log | the vendor offers it and your administrator has approved it |

If you are reading this for the first time: start with A (it is already set up), move to B the day a
second person clones the repo, and only go to C when someone asks "who can audit what Devin
asked Jira?" That question is what C is for.

## Which file the entry goes in

Devin Local reads three MCP config files. All three have the same shape (`{"mcpServers": {...}}`),
and an entry can be a local command (`command`, `args`, `env`) or a remote server (`url`,
`transport`, `headers`).

| Scope | File | Checked in? | Use it for |
| --- | --- | --- | --- |
| Project | `.devin/mcp_config.json` | yes | entries everyone who clones the repo should get (models A, B, C) |
| Local override | `.devin/mcp_config.local.json` | no (gitignored) | your personal token for a shared entry; things you are trying out |
| User | `~/.config/devin/mcp_config.json` (Windows: `%APPDATA%\devin\mcp_config.json`) | no | servers you want in every project on this machine |

Older Devin Local builds kept `mcpServers` inside `.devin/config.json`; current builds move it into
the files above on startup. If a server you added is silently ignored, check which file your build
actually read (`devin mcp list` where the CLI is present, otherwise ask Devin "which MCP servers are
registered?"). Other Devin Desktop agents document `serverUrl` for remote servers; the Devin
Local agent documents `url`. Use the key your build's documentation shows.

Secrets: write `${env:JIRA_TOKEN}` (reads your shell) or `${file:~/.secrets/jira.txt}` (reads a
file) in `env`, `headers`, `args`, or `url`. Never the value itself. An unset variable becomes an
empty string with no warning, so if a server says "unauthorized" the first thing to check is
`env | grep -c JIRA_TOKEN` (prints a count, not the value).

## Model A: on your laptop

This is what the repository ships. `.devin/mcp_config.json` starts
`integrations/reference-mcp/server.py` over stdin/stdout; no network, no token, no install.

1. `/mcp-server run-reference` shows the protocol in five JSON lines.
2. To add a tool: `/mcp-server new-tool <what it should return>`; the skill adds the schema,
   the handler, and a test.
3. To add a different local server (the Jira connector, `github-mcp-server`, `lvkit mcp`), copy
   its block from `integrations/mcp_config.example.json`, install its runtime, put the token in your
   shell, start a new Devin session.

The server runs as you, with your file permissions. Keep its tools read-only unless someone has
approved a write, and keep it reading from this repository only.

## Model B: shared definition, personal secret

Same server as A; the difference is who owns the config entry. This is the pattern the Devin Local
documentation recommends for teams:

1. The entry lives in `.devin/mcp_config.json` in the repo, with no secret in it (either no `env`
   at all, or `"JIRA_TOKEN": "${env:JIRA_TOKEN}"`).
2. Each person supplies their own credential: export it in their shell, or add an entry with the
   same name to `.devin/mcp_config.local.json` (gitignored, so it never reaches the repo). Copy the
   whole entry (`command`, `args`) and add the `env` line rather than writing `env` alone; that
   works whether your build merges the two files field by field or lets the local entry replace
   the project one. `python tools/doctor.py` fails an `env`-only override for that reason.
3. The runtime the server needs (Python, Node, a binary) is still installed per laptop. Write down
   what it is in the entry's `_comment` so the next person does not have to guess.

What you gain: one reviewed entry instead of ten hand-typed ones. What you do not gain: any central
view of who is calling what, or one place to rotate a token. Every laptop still talks to Jira as
that person.

## Model C: team-hosted, on your network

One MCP server, run by your platform team on an internal host, reached by every Devin Desktop over
HTTPS. Devin's side is small; the platform team's side is a real service.

Devin's side, one entry in `.devin/mcp_config.json` (copy `team-hosted` from
`integrations/mcp_config.example.json`):

```json
"team-tracker": {
  "url": "https://mcp.internal.example/mcp",
  "transport": "http",
  "headers": { "Authorization": "Bearer ${env:TEAM_MCP_TOKEN}" }
}
```

If the server uses your single sign-on instead of a static token, drop `headers` and run
`devin mcp login team-tracker`; a browser window opens and the token is stored locally. Devin tries
Streamable HTTP first and falls back to the older SSE transport on its own.

The platform team's side, what they have to stand up and own:

```
  laptops ──HTTPS──► reverse proxy ──► MCP server (HTTP) ──► Jira / GitLab / file share
                     │ TLS cert the     │ same three methods  │ one service account
                     │ laptops trust    │ as server.py, but   │ or per-user pass-through
                     │ auth: SSO or     │ listening on a port │
                     │ per-user token   │ instead of stdin    │
                     │ access log       │ health endpoint     │
```

| They need to decide | Why it matters |
| --- | --- |
| Hostname and TLS certificate the laptops already trust | a private CA that is not on the laptop means every connection fails with a certificate error |
| Who may reach the host (network allowlist) | Devin Desktop must be allowed outbound to it; off-network laptops lose the tools |
| Auth in front: SSO/OAuth, or a token per user | OAuth gives per-user identity and expiry; static tokens are simpler but must be issued, rotated, and revoked |
| Whose credential reaches Jira behind it | one service account means every request looks the same in Jira's audit log; pass-through keeps "who asked" but is more work |
| Logging | the reason to build C at all: one place that records tool name, caller, time, and result, in JSON, without the payload if it is sensitive |
| Read-only by default, allowlisted projects | same rules as `server.py`: validate every argument, generic errors, no writes without approval |
| Health check and who gets paged | a down host now stops every laptop, not one |
| Version and rollback | one bad deploy breaks everyone at once; keep the previous build one command away |
| Change control | this is a new system inside your boundary; expect an approval step before the first user connects |

What this repository does **not** give you: an HTTP version of the reference server, a container,
or a proxy config. `integrations/reference-mcp/server.py` is stdin/stdout only. The three methods
(initialize, list tools, call tool) and the validation rules are the same over HTTP; the
transport layer is what the platform team adds, typically with the official MCP SDK for their
language. Nothing in model C has been run here.

## Model D: vendor-hosted

Atlassian, GitLab, GitHub and others run their own MCP endpoints. The entry is a `url`, the login
is `devin mcp login <name>` in a browser, and there is nothing to host. The trade is that requests
leave your network for the vendor's cloud. Ask your administrator two things before adding one:
is the vendor endpoint approved, and is it inside your authorization boundary. If the answer to
either is no or unknown, use A or B against the offline stand-in (`integrations/fake_server.py`)
instead.

## What Devin will ask you first

`/mcp-server host` (or any request that mentions a shared, central, remote, or team MCP server)
starts with these questions, one at a time, and stops when the answers point to a model:

1. **Who else needs these tools?** Just you -> A. Your team, same repo -> B. Several teams or a
   security requirement for one log -> C. A vendor already offers it -> D.
2. **Can this laptop reach the host?** No network, or unknown -> A or B only. An internal host
   over HTTPS -> C is possible. The internet -> D is possible, with approval.
3. **Is the host approved?** For C and D Devin asks for the administrator's yes before writing an
   entry. Without it, the entry goes in `.devin/mcp_config.local.json` marked `"disabled": true`
   so nothing connects.
4. **How will you log in?** A token you export in your shell -> `headers`/`env` with `${env:...}`.
   Single sign-on -> `devin mcp login`. Neither -> stop; there is nothing safe to configure.
5. **Which file?** Just for you -> local override. Everyone who clones -> project. Every project on
   this machine -> user.
6. **Read-only?** Yes -> proceed. No -> Devin names each write tool and asks for approval for each
   before enabling it.

Devin then writes exactly one entry, with `${env:...}` placeholders and a `_comment` saying what
runtime or host it expects, shows you the diff, and tells you to start a new session so the
server list reloads. It never asks you to paste a token into the chat.

## Before you take model C to the platform or security team

Copy this into the request. Each line is something they will ask anyway.

- [ ] Which internal systems the server will read, and that it is read-only
- [ ] Which projects or paths it may return (allowlist), and who maintains that list
- [ ] Auth in front of it: SSO/OAuth or per-user tokens; how tokens are issued and revoked
- [ ] Whose credential reaches the system behind it (service account or per-user)
- [ ] Hostname, port, TLS certificate, and that laptops trust the issuer
- [ ] What is logged (tool, caller, time, outcome), where, and for how long
- [ ] Health check URL and who is on call
- [ ] How a new version is deployed and how the last one is rolled back
- [ ] The Devin-side entry, with placeholders, ready to paste into `.devin/mcp_config.json`

## Nuances that catch people

- **Permissions are separate from config.** Every MCP tool prompts for approval by default. To
  pre-approve a read-only server, add `"mcp__<server>__*"` to `permissions.allow` in
  `.devin/config.json`; to block one tool, put `"mcp__<server>__<tool>"` in `deny`.
- **A new server needs a new session.** The list is read at startup. `devin mcp list` shows what
  was registered, when the desktop offers the CLI.
- **A model A server has your permissions.** It can read anything you can. That is why the
  reference server only reads `example-system/` and validates every argument.
- **Two people, one service account (model C)** means Jira sees one user. If "who asked" matters
  to your audit, insist on per-user pass-through before going live.
- **`401` on a remote server** means "log in" (`devin mcp login <name>`), not "the server is
  broken". A `404`/`405` triggers the SSE fallback automatically; a certificate error is a trust
  problem on the laptop, not on the server.
- **Windows paths differ**: the user file is `%APPDATA%\devin\mcp_config.json`, and shell secrets
  are set with `$env:JIRA_TOKEN="..."`.

## Not verified in this repository

Model A is exercised by `integrations/reference-mcp/test_server.py` and `tools/doctor.py` (which
reads the project file, the local override, and the user file when present, validates `url`
entries, and rejects literal tokens in `headers` or `env`). The file locations,
`${env:...}`/`${file:...}` interpolation, `url`/`transport`/`headers` fields, the SSE fallback, and
`devin mcp` commands above come from the Devin Local documentation
(https://docs.devin.ai/cli/extensibility/mcp/configuration) and were not run here; confirm them
against the build installed on your laptop. No HTTP MCP server, reverse proxy, OAuth flow, or
vendor endpoint has been tested in this repository, and nothing here has been run inside a
customer's network.
