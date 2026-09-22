# Live walkthrough (about 25 minutes)

A speaker path for showing this repository in Devin Desktop. Short beats, one paste each, a line to
say while it runs, and a recovery move if something stalls. Everything is offline.

## Before you start (5 minutes, no audience)

- Fresh clone, open the folder in Devin Desktop, one terminal.
- `python tools/doctor.py` says READY. `python tools/check_repo.py` says OK. If not, fix that first.
- Zoom the font up. Close everything else. Have `README.md` open in a tab.

## Beat 1: the tour (3 min)

Paste: `Reference this repo. What can you do here? Run the checks and show me.`

Say: this is a plain folder. Nothing to install, no network. Devin reads one file, `AGENTS.md`, and
counts the skills. Watch it check the laptop, run every test, and open a deck it did not write yet.

Point at: the doctor table, the `OK:` line, the deck in the preview. Hit the right arrow twice.

Recovery: if the skill list did not come up, paste `python tools/check_repo.py` in the terminal
yourself and keep talking. The repo proves itself either way.

## Beat 2: what if we change a part (5 min)

Paste: `/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN`

Say: this is the question every embedded team gets on a Tuesday. The part data is six small JSON
files. Devin recomputes the power and timing budgets, checks the interface, and reads the hazard
table. The numbers come from a script, not from the model.

Point at: the verdict line (go, no-go, or go with conditions), the before/after power table, the
hazards it says change. Ask the room: is that the analysis you do by hand today?

Recovery: `python tools/what_if.py --imu imu-c --uplink can-xcvr --markdown` prints the same table.

## Beat 3: brief leadership (4 min)

Paste: `/exec-deck Design review deck for the imu-c + CAN change: verdict, budgets, hazards, open items`

Say: same material, different audience. One idea per slide, a source line under every number. It is
a single HTML file, so it opens anywhere and prints to PDF with `P`.

Point at: the stats slide, the two-column trade slide, the footer that says synthetic. Press `P`.

Recovery: `python tools/build_deck.py templates/deck-outline-example.json outputs/example-deck.html`
and open the file. The shape is identical.

## Beat 4: tests first on firmware (5 min)

Paste: `/tdd Make the temperature fault flag stay set until two in-range readings`

Say: two twins of the same firmware, C and Python, same tests. Devin writes the failing test first,
you will see it go red, then the smallest change to both twins, then green. Hardware is a callback,
so this runs on a laptop.

Point at: the red run, the green run, `make -C example-system test` at the end. Both languages.

Recovery: `make -C example-system test` shows the current suite passing. Move on; the diff is the
point, not the wait.

## Beat 5: research with receipts (3 min)

Paste: `/research-brief Should we swap IMU A for IMU B? --sources example-system/parts,example-system/docs`

Say: every finding has a source id and a confidence. The renderer rejects a claim without a source.
That is the rule for analyst work here: no source, no finding.

Point at: the findings table, the open questions, the `.html` brief.

## Beat 6: connect to your tools, safely (3 min)

Paste: `/connect-tools I have a GitLab PAT; pull open issues for project 123 read-only`

Say: the token never goes in chat. Devin asks you to export it in the shell, then shows the request
with the token redacted before anything is sent. Read-only by default. CLI, REST, and MCP are three
lanes to the same place; pick the one your admin has approved.

Point at: the dry-run request, `integrations/README.md` lane table.

Recovery: this beat is a dry run by design. Nothing needs to be online.

## Beat 7: an MCP server, by hand (2 min)

Paste: `/mcp-server run-reference`

Say: an MCP server is a program that answers three questions over stdin. Here is one in one file,
no dependencies. Five lines of JSON and you have seen the whole protocol. Adding a tool is a
function and a test.

Point at: the five JSON lines, `.devin/mcp_config.json`.

## Close (1 min)

Say: fork it, open it, paste `Mimic workflow 1 on ../your-firmware`. The skills are generic; the
example system is just the thing they practise on.

Ask them: which of the five workflows in `WORKFLOWS.md` is closest to what your team does weekly?
What is the artifact you rewrite most often? Who has to approve a token?

## If the slash commands are not recognised

Every row in `AGENTS.md` has a plain-English trigger. Say "make me a deck" instead of `/exec-deck`;
Devin routes it the same way. Nothing in the walkthrough depends on the slash form.
