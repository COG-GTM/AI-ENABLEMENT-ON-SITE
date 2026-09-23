# Connecting to Jira on-premises (Jira Data Center): every option, for a first-time user

This page is for someone who has never used Devin, has never heard of MCP, and has been told
"we run Jira on-prem, connect to it". It lists every way to do that, says which one to pick, walks
through the command-line path step by step, and explains what your Jira administrator has to do on
their side. Everything here is read-only. Nothing in this repository has been run against a real Jira
Data Center host; the section "What was tested" says exactly what was.

**Which Jira do you have?** "On-prem" means **Jira Data Center** (or the retired Jira Server; the
API is the same). If your Jira address ends in `.atlassian.net`, you have **Jira Cloud** and this page
is the wrong one; use `curl-recipes.md` (Cloud rows) and `cli-recipes.md` (`acli`). Not sure? Ask your
administrator, or open `https://<your-jira>/rest/api/2/serverInfo` in a browser while logged in:
Cloud answers `"deploymentType": "Cloud"`; Data Center answers something else (`"Server"` on the versions seen so far).

## Words you will see

| Word | Meaning here |
| --- | --- |
| **Jira Data Center (DC)** | Jira installed on servers your organisation runs (on-premises or in your own cloud tenancy). You reach it at an address like `https://jira.example.internal`. |
| **Jira Cloud** | Jira hosted by Atlassian at `https://<site>.atlassian.net`. Different login, different API version. Not this page. |
| **REST API** | The web address Jira answers programs on: `https://<your-jira>/rest/api/2/...`. It returns JSON instead of a web page. Jira DC ships with it; there is nothing extra to install. |
| **PAT** (personal access token) | A long random string you create in your Jira profile and use instead of your password from scripts. It can expire, it can be revoked, it inherits your permissions. Never paste one into a chat. |
| **CLI** | A command-line program you run in a terminal (`jira issue list`). Every CLI on this page is just a program that calls the REST API for you. |
| **MCP** | A small server that gives Devin named "tools" (search issues, read one issue) so you do not have to explain the API in every session. `mcp-hosting.md` covers where it can live. |
| **Devin** | The agent that runs commands on your laptop (Devin Desktop / Devin Local) or in Cognition's cloud. In this repository Devin runs the commands below and shows you each one first. |
| **Lane** | This repository's word for the transport: offline files, REST/curl, vendor CLI, or MCP. Lane and credential are separate choices. |

## The one picture

Every option on this page is a client on your side of the line talking to the same Jira REST API.
Jira does not have a command line of its own and does not need one for any of these to work.

```
   your laptop (Devin Desktop runs the commands)                      your network            Jira Data Center
  ┌────────────────────────────────────────────┐                    ┌───────────┐          ┌──────────────────────┐
  │ 1 curl ─────────────────────────────────┐  │                    │ firewall/ │          │ web UI      /browse  │
  │ 2 integrations/rest_client.py ──────────┤  │  HTTPS + PAT       │ proxy /   │          │ REST API    /rest/   │
  │ 3 jira-cli (open source) ───────────────┼──┼── Authorization: ─►│ VPN /     │─────────►│  api/2/myself        │
  │ 4 Appfire Jira CLI (commercial) ────────┤  │  Bearer <PAT>      │ allowlist │          │  api/2/serverInfo    │
  │ 5 go-jira (older open source) ──────────┤  │                    └───────────┘          │  api/2/search        │
  │ 6 MCP server (local, model A/B) ────────┘  │                                           │  api/2/issue/{key}   │
  └────────────────────────────────────────────┘                                           │  agile/1.0/board     │
  ┌────────────────────────────────────────────┐                                           │                      │
  │ 6 MCP server (team-hosted, model C) ───────┼──────────────────────────────────────────►│ (option 4 only:      │
  └────────────────────────────────────────────┘                                           │  ACLI Connector app  │
  ┌────────────────────────────────────────────┐                                           │  installed by admin) │
  │ 0 offline: fake_server.py on 127.0.0.1     │  no network, no real token                └──────────────────────┘
  └────────────────────────────────────────────┘
```

Two things decide whether any of 1-6 works, and neither is about the client you pick:

1. **Reach.** Can your laptop open an HTTPS connection to the Jira address? (Firewall, VPN, proxy, allowlist.)
2. **Credential.** Do you have a PAT Jira accepts, and does your Jira account have permission to see the projects you ask about?

Prove those two with option 1 (`curl`) first. Once `curl` gets a `200`, every other option is a matter of installing software.

## What your Jira administrator has to expose or configure

The question people ask is "does our Jira need to expose an API, or install a CLI?". The answer for
Jira Data Center:

- **The REST API is already there.** It is part of the Jira web application and answers on the same
  address and port as the web UI (`https://<your-jira>/rest/api/2/...`, and `/rest/agile/1.0/...` for
  boards and sprints). If you can log in to Jira in a browser from your laptop, the API is reachable
  from your laptop. Nothing has to be "turned on" for it, and there is no separate API server.
- **Jira has no CLI of its own.** Every command-line tool on this page is a client program you install
  on your laptop. The only server-side piece any of them needs is option 4 (Appfire), which requires
  its "ACLI Connector" Marketplace app installed in Jira by an administrator and a commercial licence.
  If you choose options 1, 2, 3, 5, or 6, the administrator installs nothing in Jira.

What the administrator does have to provide or confirm (hand them this list):

| # | Item | Why | How to check from the laptop |
| --- | --- | --- | --- |
| 1 | The user-facing Jira base URL (`https://jira.example.internal`, sometimes with a context path such as `/jira`) | Every call is `BASE + /rest/...`. An internal node address or load-balancer name may not carry the right certificate or session handling | Ask; it is the address in your browser's bar when you are in Jira |
| 2 | Outbound HTTPS from your laptop (or the Devin runtime) to that host: firewall rules, VPN, proxy settings, IP or hostname allowlist | Without reach every option fails the same way (timeout / connection refused) | `curl -sS -o /dev/null -w "%{http_code}\n" "$JIRA_BASE/rest/api/2/serverInfo"` returns a number (200 or 401), not a network error |
| 3 | Personal access tokens enabled | PATs exist from Jira 8.14; the `atlassian.pats.enabled` system property switches them on or off for the whole instance, and some SSO deployments switch them off. Admins can also cap token lifetime | Profile menu > **Personal Access Tokens** shows a **Create token** button |
| 4 | Your Jira account has **Browse Projects** on the projects you need | A PAT carries your permissions, no more; a `200` on `/myself` and a `404` on an issue key means "you cannot see that project" | `GET /rest/api/2/issue/<key>` for a key you can open in the browser |
| 5 | TLS certificate from a CA your laptop trusts, or the CA bundle to trust | Private CAs are normal on-prem; without the bundle every client reports a certificate error | `curl` prints `SSL certificate problem` -> ask for the PEM bundle, then `--cacert`, `REST_CA_BUNDLE`, or the OS trust store |
| 6 | Proxy settings, if the network needs them | Clients read `HTTPS_PROXY` / `NO_PROXY`; a corporate proxy may also need the Jira host on `NO_PROXY` | `env \| grep -i proxy` |
| 7 | (Option 4 only) Appfire ACLI Connector app installed and licensed in Jira | Appfire's CLI talks to that app; without it the CLI cannot connect | Jira admin > Manage apps |
| 8 | (Option 6, model C only) A host to run the MCP server, a certificate for it, and a decision on whose credential it uses | Covered in `mcp-hosting.md` | n/a |
| 9 | Authorisation: is Jira, and the network path to it, approved for this desktop and for Devin? | Nothing here is inside an authorisation boundary by default (`README.md`, "Boundary reminder") | Ask before the first live call |

Nothing on this list writes to Jira, and every recipe below is GET-only. If an administrator wants
proof, `integrations/fake_server.py` is the read-only subset this repository exercises, and
`tools/tests/test_integrations.py` asserts that every non-GET is refused.

### How a PAT works (so you can explain it to your admin)

1. You log in to Jira in a browser, open your profile, **Personal Access Tokens**, **Create token**, give it a name and an expiry.
2. Jira shows the token once. You put it in an environment variable in your terminal (`export JIRA_TOKEN=...`), never in a file in this repository and never in a chat.
3. Every request carries `Authorization: Bearer <token>`. Jira looks the token up, finds you, and applies your permissions.
4. Revoke it from the same page when you are done; a leaked PAT is revoked the same way.

Jira Cloud does **not** use this header (it uses `Basic email:api-token`); if a guide tells you to use
your email address, it is a Cloud guide.

## All the options

Cheapest first. Start at the top and move down only when you have a reason.

| # | Option | What it is | Install on the laptop | Install in Jira | Credential | Tested in this repository |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | **Offline practice** | `integrations/fake_server.py` serves the Jira DC read endpoints on `127.0.0.1` from synthetic data | nothing (Python 3) | nothing | a fake token | yes: every step below, plus jira-cli, was run against it |
| 1 | **REST with `curl`** | Type the URL yourself; `curl-recipes.md` | `curl` (already on most laptops) | nothing | PAT | yes, against the fake |
| 2 | **REST with `rest_client.py`** | Same calls, but the script checks the URL, redacts the token, walks every page, and refuses non-GET | nothing (Python 3, standard library) | nothing | PAT | yes, against the fake (`test_integrations.py`) |
| 3 | **`jira-cli`** (open source, Go, single binary) | `jira issue list`, `jira issue view SN-101`, JSON/CSV output; supports Data Center with PAT (`bearer`), password (`basic`), or client certificates (`mtls`) | one binary from the releases page | nothing | PAT | yes: v1.7.0 `init`, `issue list`, `issue view` against the fake |
| 4 | **Appfire Jira CLI** (commercial, formerly Bob Swift) | Vendor CLI for Server and Data Center with hundreds of actions | the CLI package (Java) | **yes**: ACLI Connector app, licensed | Jira user + PAT/password per Appfire docs | no: needs a licence and an admin-installed app |
| 5 | **`go-jira`** (older open source, Go) | Command-line client for Jira Server/DC REST; smaller community than option 3 | Go toolchain to build, or a release binary | nothing | PAT or password | no: Go is not installed here |
| 6 | **MCP server** (Devin tools) | A read-only Jira connector Devin calls as tools; four hosting models in `mcp-hosting.md`; worked example `COG-GTM/jira-mcp` | A/B: Docker or Python + the connector; C/D: nothing | nothing | A/B: PAT from env; C: token header or SSO; D: OAuth | reference MCP server yes; `jira-mcp` against the fake yes; against real Jira no |
| - | **Atlassian `acli`** | Atlassian's own CLI | | | | **Do not use for Data Center.** Atlassian documents it for Cloud sites (`*.atlassian.net`, email + API token) only. It is listed so you do not pick it by mistake. |
| - | **Devin's hosted Jira integration** (Devin web app, Settings > Integrations) | Cognition-hosted sign-in to Atlassian | | | | Built around Atlassian Cloud sign-in. Not verified against a Data Center host in this repository; assume it does not reach a Jira behind your firewall unless Cognition confirms it for your deployment. |

### Which one should a new user pick?

```
                 Do you have a PAT and can curl reach Jira?
                                 │
                 no ─────────────┴───────────── yes
                 │                               │
       Option 0: practice offline      Do you need to type JQL yourself
       while the admin sorts           and keep the fewest moving parts?
       reach and PAT (this page,               │
       "Offline first")                yes ─────┴───── no
                                        │               │
                              Option 1 or 2       Is installing one binary allowed?
                              (curl / rest_client)        │
                                                  yes ────┴──── no
                                                   │              │
                                        Option 3 (jira-cli)   Option 2 (rest_client.py)
                                                   │
                            Will Devin ask Jira many times per session?
                                        yes ───────┴─────── no
                                         │                   │
                               Option 6 (MCP, model A/B)   stay on 3
```

Option 4 is for organisations that already own the Appfire licence and want its bulk actions;
option 5 only if option 3 is not permitted and you already have Go. Option 6 models C and D need
platform and security team involvement first (`mcp-hosting.md`).

## Offline first: rehearse every step with no network and no token

Terminal 1 (leave it running):

```bash
python integrations/fake_server.py --port 8089       # prints 8089; Ctrl-C stops it
```

Terminal 2. This is the same shape you will use for the real Jira; only the two variables change:

```bash
export JIRA_BASE=http://127.0.0.1:8089                  # real: https://jira.example.internal
export JIRA_TOKEN=fake-token-for-local-tests            # real: your PAT, pasted at runtime, never into a file
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/myself"
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/serverInfo"
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/issue/SN-103"
```

Expected: three JSON documents. `myself` names `practice-user`; `serverInfo` says version `10.3.0`,
`deploymentType` `Server`; the issue is `SN-103`, status `In Progress`. Now break it on purpose:

```bash
curl -sS -H "Authorization: Bearer wrong-value" "$JIRA_BASE/rest/api/2/myself"        # 401 JSON, token not echoed
curl -sS -X POST -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/issue"  # 405: the fake has no write path
```

The fake serves: `/rest/api/2/myself`, `/serverInfo`, `/search`, `/issue/{key}`, `/project`, `/field`,
`/issue/createmeta/{key}/issuetypes`, and `/rest/agile/1.0/board` (always empty). That is the set a
CLI touches to start up and list issues; anything else is `404`. JQL is limited to `project`,
`status`, `statusCategory`, `issuetype`/`type` with `=`, `!=`, `IN`, `NOT IN`, joined by `AND`.

## Step by step: the first real connection (options 1 and 2)

Do these in order. Stop at the first one that fails and take the row from the troubleshooting table.

**Step 1. Get the three facts.** From your administrator: the base URL, confirmation that HTTPS from
your laptop to it is allowed, and confirmation that PATs are enabled. From yourself: which project key
you are allowed to read (the letters before the dash in an issue key, `SN` in `SN-103`).

**Step 2. Create a PAT.** Jira, profile picture (top right), **Personal Access Tokens**, **Create
token**. Name it for the laptop and purpose, set an expiry (30-90 days), copy the value once.

**Step 3. Put it in the terminal, not a file.**

```bash
export JIRA_BASE="https://jira.example.internal"     # include the context path if your Jira has one, e.g. https://tools.example.internal/jira
export JIRA_TOKEN="<paste here>"
env | grep -c JIRA_TOKEN                             # prints 1, not the value; this is how Devin confirms it exists
```

Windows PowerShell: `$env:JIRA_BASE="https://jira.example.internal"`, `$env:JIRA_TOKEN="<paste here>"`.

**Step 4. Reach, without the token.** A number back means the network path works; the number will be `401`.

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "$JIRA_BASE/rest/api/2/serverInfo"
```

**Step 5. Identity, with the token.** `200` and your own account means reach, PAT, and TLS are all right.

```bash
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/myself" | python -m json.tool
```

**Step 6. Data.** One issue you can see in the browser, then a search. Percent-encode the JQL
(`%3D` is `=`, `%20` is a space) or let `rest_client.py` do it.

```bash
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_BASE/rest/api/2/issue/SN-103"
curl -sS -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_BASE/rest/api/2/search?jql=project%3DSN%20AND%20status%3D%22In%20Progress%22&maxResults=20&fields=key,summary,status,priority"
```

**Step 7. Same thing through the repository script**, which redacts the token, refuses plain
`http://` for anything but `127.0.0.1`, fetches every page, and never sends anything but GET:

```bash
python integrations/rest_client.py --dry-run jira issue SN-103        # shows the request; token is <redacted>
python integrations/rest_client.py jira issue SN-103
python integrations/rest_client.py jira search "project = SN AND status = 'In Progress'" > outputs/jira-open.json
python tools/tracker_import.py --from jira --in outputs/jira-open.json --out outputs/tracker-jira.json
python tools/tracker_report.py --file outputs/tracker-jira.json --markdown
```

Private CA: `export REST_CA_BUNDLE=/path/to/corporate-ca.pem` for the script, `--cacert` for `curl`.

**Step 8. Clean up.** Close the terminal (the variables die with it). Check `history | grep -c JIRA_TOKEN=`
shows only the `export` line, and revoke the PAT when the work is done.

## Step by step: the command-line client (option 3, `jira-cli`)

`jira-cli` is an open-source Go program (github.com/ankitpokhrel/jira-cli). It is one binary, needs
nothing installed in Jira, and its documentation names "on-premise installation" with `bearer` (PAT)
authentication for Data Center. Version 1.7.0 was run against the offline fake below; the sequence
against a real Jira is identical except for the two variables.

**Install.** Download the archive for your OS from the project's releases page (`jira_<version>_linux_x86_64.tar.gz`,
`..._darwin_...`, `..._windows_...`), unpack, and put `bin/jira` on your `PATH` (or call it by path).
Check: `jira version` prints `Version="1.7.0"` or later. On a locked-down laptop, this download is the
step to get approved; there is no other install.

**Configure.** The token is read from `JIRA_API_TOKEN`; `JIRA_AUTH_TYPE=bearer` tells it to send
`Authorization: Bearer`. Then `init` asks Jira who you are and which projects you can see:

```bash
export JIRA_API_TOKEN="$JIRA_TOKEN"                    # or paste the PAT here at runtime
export JIRA_AUTH_TYPE=bearer
jira init --installation local --server "$JIRA_BASE" --login <your-jira-username> \
          --auth-type bearer --project SN --board none
```

- `--installation local` is jira-cli's name for Data Center / Server; `cloud` would send Cloud-style auth and fail.
- `--login` is your Jira **username** (not email) for Data Center.
- `--board none` skips picking an Agile board; add one later with `jira init` again if you use sprints.
- `--insecure` exists for self-signed certificates. Do not use it; ask for the CA bundle instead. On
  Linux, Go programs such as jira-cli honour `SSL_CERT_FILE=/path/to/corporate-ca.pem`; on Windows and macOS
  import the CA into the OS trust store. (Not exercised here; the fake is plain HTTP on `127.0.0.1`.)
- Config lands in `~/.config/.jira/.config.yml` (override with `JIRA_CONFIG_FILE`). It stores the server,
  login, project, and issue types; **the token stays in the environment variable**, not in the file.

What `init` sends, recorded against the fake (all GET):

```
GET /rest/api/2/myself
GET /rest/api/2/serverInfo
GET /rest/api/2/project?expand=lead
GET /rest/agile/1.0/board?projectKeyOrId=SN
GET /rest/api/2/issue/createmeta/SN/issuetypes?expand=projects.issuetypes.fields
GET /rest/api/2/field
```

So if `init` fails, the log on the Jira (or proxy) side shows exactly which of those six was refused.

**Read.** Every command below is a GET. `--plain` gives a table, `--raw` JSON, `--csv` CSV.

```bash
jira me                                   # who the token belongs to (from the saved config)
jira serverinfo                           # version, deployment type
jira issue list --plain                   # default project, newest first
jira issue list -s "In Progress" --plain  # by status
jira issue list -tBug --plain             # by type
jira issue view SN-103 --plain            # one issue
jira issue list -s Done --csv > outputs/jira-done.csv
```

`--raw` prints jira-cli's own reshaped JSON (an array, with `issueType` instead of Jira's `issuetype`),
not the Jira response, so `tools/tracker_import.py --from jira` rejects it. To feed the tracker, take the
same JQL through `python integrations/rest_client.py jira search "..."` (step 7 above); use jira-cli for reading and `--csv` for spreadsheets.

**Do not run** `jira issue create`, `edit`, `move`, `assign`, `comment add`, `delete`, or `sprint add`:
they write to Jira. The repository rule is read-only until a user approves a specific write with a
scoped token. (Against the fake these stop with `404` on the transitions endpoint and `405` on any POST.)

### Transcript against the offline fake (jira-cli 1.7.0, 2026-09)

```
$ jira init --installation local --server http://127.0.0.1:8089 --login practice-user --auth-type bearer --project SN --board none --force
Configuration generated: /home/<you>/.config/.jira/.config.yml

$ jira issue list -s "In Progress" --plain
TYPE    KEY     SUMMARY                                                             STATUS
Defect  SN-103  MCU busy-waits between samples; sleep mode not entered              In Progress
Bug     SN-104  IMU reinit counter not reported in any packet field                 In Progress
Story   SN-106  Implement low-power sleep between samples                           In Progress
Story   SN-107  CAN uplink option for multi-node deployments                        In Progress
Story   SN-108  Evaluate IMU B as lower-power drop-in replacement                   In Progress
Bug     SN-112  CRC mismatch counter wraps at 255 and hides sustained link faults   In Progress

$ JIRA_API_TOKEN=wrong-value jira issue list --plain
jira: Received unexpected response '401 Unauthorized'.
Please check the parameters you supplied and try again.

$ jira issue comment add SN-103 "x"          # a write: the fake has no POST path
jira: Received unexpected response '405 Method Not Allowed'.
```

## Option 4: Appfire Jira CLI (commercial)

Appfire's "Jira Command Line Interface (CLI)" is the long-standing commercial CLI for Jira Server and
Data Center (the Marketplace listing names Cloud, Server, and Data Center; the compatibility page lists
the supported Data Center versions). Two things make it different from everything else on this page:

- **It needs a server-side app.** Appfire's licensing page says most ACLI clients require the **ACLI
  Connector** app installed on the Atlassian instance. A Jira administrator installs and licenses it
  from **Manage apps**. Without it the CLI has nothing to talk to.
- **It is licensed.** Both the connector and the client are commercial.

Pick it when your organisation already owns it or needs its bulk actions (thousands of issues, CSV
round-trips, workflow administration). Otherwise option 3 gets a new user reading issues with no
Jira-side change. Not tested in this repository: no licence and no Jira to install the connector in.
Follow Appfire's own install and connection guide; the same PAT, reach, and TLS checklist above
applies, plus row 7.

## Option 5: `go-jira`

`go-jira` (github.com/go-jira/jira) is an older open-source Go client that speaks the same REST API and
supports Server/Data Center. It has a smaller community and slower release cadence than option 3, and
it needs a Go toolchain unless a release binary exists for your OS. Not run here (Go is not installed on
this machine). Consider it only if option 3 is refused and you already build Go software.

## Option 6: MCP, so Devin has Jira as tools

An MCP server turns the same GET calls into named tools Devin can call in any session
(`jira_search`, `jira_get_issue`). Nothing about Jira changes; the four models differ in **where the
server runs and whose token it holds** (`mcp-hosting.md` has the full picture and the questions Devin
asks first):

| Model | Where the server runs | Token | Laptop install | Jira admin | Tested here |
| --- | --- | --- | --- | --- | --- |
| A. On your laptop | a Python/Node process Devin starts | your PAT via `${env:JIRA_TOKEN}` | runtime + connector | nothing | reference server yes; `jira-mcp` connector against the fake yes (below) |
| B. Shared definition, personal secret | same as A, config committed, secret per person | `${env:JIRA_TOKEN}` / `${file:...}` | same as A | nothing | no |
| C. Team-hosted | an internal host behind your reverse proxy | a service account **or** pass-through per user | nothing | host, certificate, and the audit question "who asked?" | no |
| D. Vendor-hosted | on the internet | OAuth in the browser | nothing | authorisation-boundary decision; requests leave your network | no |

Whatever connector you use, the handover checklist applies: every tool GET-only, allowlist applied on
every endpoint (Agile ones included), pagination completed before filtering, no token in the file.
`/mcp-server` walks through registering it.

### Worked example of model A: the self-hosted `jira-mcp` connector

`https://github.com/COG-GTM/jira-mcp` is a small, generic, read-only Jira Data Center MCP server written
for exactly this setup: the engineer runs it on their own machine inside the network, Devin Desktop
talks to it over stdio, and it talks to Jira over HTTPS with a PAT. It is an example, not an Atlassian
product: read its code, have your security reviewer and Jira administrator look at it, and fork it if
your rules differ.

```text
  your laptop (inside the network)                                       your network
  ┌──────────────────────────────────────────────────────────────┐      ┌──────────────────┐
  │  Devin Desktop ──stdio (MCP)──► docker run -i onprem-jira-mcp │──HTTPS──►│ Jira Data Center │
  │                                  (or: python -m connector.server)│  PAT  │ /rest/api/2/...  │
  │  no inbound port opened; the PAT is passed at launch, not baked│      │ /rest/agile/1.0/ │
  └──────────────────────────────────────────────────────────────┘      └──────────────────┘
```

What it gives Devin (seven tools, all GET): `search_issues(jql, limit)`, `get_issue(key)`,
`get_comments(key)`, `list_projects()`, `list_fields()`, `get_boards()`, `get_sprint_issues(sprint_id)`.

What it does that the handover checklist asks for:

| Control | How the connector does it |
| --- | --- |
| Read-only | Only the seven GET-backed tools exist; there is no create/update/transition/delete tool to misuse |
| Project allowlist | `JIRA_PROJECTS=SN,ABC`; every JQL is rewritten to `(<your jql>) AND project in ("SN","ABC")`, `get_issue`/`get_comments` refuse keys outside the list, boards and sprint issues are filtered to it |
| Input checks | Issue keys must look like `ABC-123`; sprint ids must be numeric |
| Credential handling | `JIRA_TOKEN` (or `JIRA_USERNAME`/`JIRA_PASSWORD` with `JIRA_AUTH_MODE=basic`) is read from the environment at start, never written to disk or the image, and redacted from every log line and error |
| TLS | verifies by default (`JIRA_SSL_VERIFY=true`); a private CA is `JIRA_CA_BUNDLE=/path/to/ca.pem` mounted into the container |
| Audit | one JSON line per call on stderr: tool, target, ok/refused/error, duration; no payloads |
| Network surface | stdio only, so nothing listens on a port; outbound HTTPS to Jira is the only connection |

How you run it (its `DEPLOYMENT.md` has the six steps in full; the credential comes from your Jira
administrator per row 3 above):

```bash
git clone https://github.com/COG-GTM/jira-mcp ../jira-mcp && cd ../jira-mcp
docker build -t onprem-jira-mcp:latest .           # or: pip install -r requirements.txt  (mcp, httpx)
# Devin Desktop: copy the "onprem-jira" block from devin-desktop.example.json into your MCP config,
# set JIRA_URL, JIRA_PROJECTS, and point JIRA_TOKEN at your PAT with ${env:JIRA_TOKEN}.
```

This repository's `mcp_config.example.json` carries the same block as `jira-readonly`. Two things to
know before you copy it: the Python form must be started as a module from the connector's own
directory (`python -m connector.server`; running `connector/server.py` directly fails with a relative
import error), which is why the example uses the Docker form; and `JIRA_URL` is the browser-bar base
URL from row 1, context path included.

Tested here (offline, 2026-09, `jira-mcp` commit `cf7fa17`): its own test suite (37 tests) passes;
pointed at the fake with `JIRA_URL=http://127.0.0.1:8089` and `JIRA_PROJECTS=SN`, the MCP tool listing returned
the seven tools, `list_projects`, `get_issue SN-103`, `search_issues status = 'In Progress'` (6 hits)
and `get_boards` returned the fake's data, `get_issue ZZ-1` was refused by the allowlist before any
request left the laptop, a wrong token surfaced as `Jira returned 401` with the token absent from the
error and the log, and the audit lines were as described. The fake learned parenthesised JQL groups for
this (`(status = 'In Progress') AND project in ("SN")`). Not tested: a real Jira host, the Docker image
build, `basic` mode, `JIRA_CA_BUNDLE`, `get_comments` and `get_sprint_issues` (the fake has no comments
or sprints).

For a brand-new user: get option 1 or 3 working first. MCP is a convenience layer on top of a working
connection, not a way around a missing one.

## Troubleshooting: what the number means

| You see | Means | Do |
| --- | --- | --- |
| `curl: (6) Could not resolve host` | DNS: the laptop cannot find the name | VPN? Correct hostname? Ask the admin (row 2) |
| `curl: (7) Failed to connect` or `(28) timed out` | Network path blocked or host down | Firewall/proxy/allowlist (row 2); try from a browser on the same laptop |
| `curl: (60) SSL certificate problem` | Private CA not trusted | Get the CA bundle; `--cacert`, `REST_CA_BUNDLE`, OS trust store (row 5). Never `-k` / `--insecure` |
| `401` on `/myself` | Token missing, expired, revoked, PATs disabled, or Cloud-style `Basic` sent to Data Center | New PAT; confirm `Authorization: Bearer`; confirm PATs enabled (row 3) |
| `403` | Authenticated, but not allowed (a permission scheme, or Jira asking for a CAPTCHA after failed browser logins) | Log in once in the browser; ask for Browse Projects (row 4) |
| `404` on an issue or `/issue/createmeta/<key>` | Wrong key, or you cannot see that project (Jira hides existence) | Check the key in the browser; row 4 |
| `404` on `/rest/api/2/serverInfo` itself | Wrong base URL: missing context path or an internal address | Use the browser-bar address (row 1) |
| `302` / an HTML login page instead of JSON | SSO redirect: the request had no valid credential | Send the PAT header; if it still redirects, PATs may be disabled (row 3) |
| `429` | Rate limiting | Slow down, smaller `maxResults`, fewer parallel calls |
| `jira init`: `Received unexpected response '404 Not Found'` | One of the six startup GETs is not served (very old Jira, reverse-proxy path rule) | Compare the list above with the Jira access log |
| jira-cli `x509: certificate signed by unknown authority` | Same as the `curl` (60) row | `SSL_CERT_FILE` (Linux) or OS trust store; not `--insecure` |
| `rest_client.py`: `refusing non-HTTPS URL` | Base URL is `http://` and not `127.0.0.1` | Use `https://`; plain HTTP is only for the fake |

## What was tested, and what was not

Tested on this machine (Linux, Python 3.12, no network to any Jira), all against
`integrations/fake_server.py` with the synthetic fixtures:

- `curl` and `rest_client.py`: `/myself`, `/serverInfo`, `/search` with paging, `/issue/{key}`; wrong token -> `401` with no token in the body or log; `POST` -> `405`. Asserted in `tools/tests/test_integrations.py`.
- `jira-cli` v1.7.0 (GitCommit `79067e2`, 2025-08-30, linux/amd64): `init --installation local --auth-type bearer`, `me`, `serverinfo`, `issue list` (plain, by status, by type, `--raw`, `--csv`), `issue view`; wrong token -> `401`. The six GETs `init` makes are recorded above and served by the fake.
- The fake's new Data Center routes (`/myself`, `/serverInfo`, `/project`, `/field`, `/issue/createmeta/{key}/issuetypes`, `/rest/agile/1.0/board`) and its `IN` / `NOT IN` JQL and parenthesised groups, each with a valid token, a wrong token, and no token.
- The self-hosted `COG-GTM/jira-mcp` connector (commit `cf7fa17`, Python form, MCP over stdio) against the fake: tool list, `list_projects`, `get_issue`, `search_issues`, `get_boards`, allowlist refusal, wrong token -> `401` with no token in error or log. Its own 37 tests pass.

Not tested (needs something this repository does not have):

- Any real Jira Data Center host, PAT, private CA, proxy, or SSO redirect: the "Onsite-only live check" in `README.md` is the list to run when you have them.
- Appfire Jira CLI (licence + admin-installed connector) and `go-jira` (Go toolchain).
- `jira-cli` `basic` and `mtls` authentication, `SSL_CERT_FILE`, Windows and macOS binaries.
- Any MCP server against a real Jira host, the `jira-mcp` Docker image build, and models C and D end to end.
- Devin's hosted Jira integration against a Data Center host.

## Sources (each opened and checked 2026-09)

- Jira Data Center REST API reference (v2 platform): https://developer.atlassian.com/server/jira/platform/rest/v11002/ ; `myself`: https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-myself/ ; `serverInfo`: https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-serverinfo/ ; search: https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-search/ ; issue: https://developer.atlassian.com/server/jira/platform/rest/v11002/api-group-issue/
- Personal access tokens in Data Center (Bearer header, 8.14+, `atlassian.pats.enabled`, expiry): https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html
- Atlassian `acli` is documented for Cloud: https://developer.atlassian.com/cloud/acli/guides/introduction/ and https://developer.atlassian.com/cloud/acli/guides/frequently-asked-questions/
- Appfire Jira CLI: Marketplace listing https://marketplace.atlassian.com/apps/6398/jira-command-line-interface-cli ; Data Center compatibility https://appfire.atlassian.net/wiki/spaces/ACLI/pages/3380838441/Compatibility+for+ACLI+13.1.0 ; licensing and the ACLI Connector requirement https://appfire.atlassian.net/wiki/spaces/ACLI/pages/60559747/Licensing+and+connector+requirements
- `jira-cli` (on-premise support, `basic` / `bearer` / `mtls`): https://github.com/ankitpokhrel/jira-cli ; releases: https://github.com/ankitpokhrel/jira-cli/releases
- `go-jira`: https://github.com/go-jira/jira
- Self-hosted read-only Jira Data Center MCP connector (example for option 6, model A/B): https://github.com/COG-GTM/jira-mcp (access is by organisation; it returned 404 anonymously when checked)
