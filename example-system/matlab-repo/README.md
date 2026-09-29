# MATLAB repository fixture

Offline sample input for `/repo-discovery` and `tools/m_fleet_scan.py`: a small synthetic MATLAB code base
(27 `.m` files, hand-written, no toolbox required to read) shaped like a test-bench soak analysis: load a
recording, decode packets, calibrate, filter, check limits, write a report. Nothing here runs in this
repository; MATLAB is not installed and is not needed. The single-model fixture the `/matlab-to-code` skill
uses is `../model/`; this tree is for the *repository-scale* question: what is in here, what calls what,
where do we start.

Every construct that makes repository-scale MATLAB discovery hard on a real tree is present on purpose, so
the scanner's output shows how each one is reported rather than guessed:

| Construct | Where | What the scanner does |
| --- | --- | --- |
| Scripts vs functions vs script-with-local-functions | `run_soak.m`, `setup_paths.m`, `tests/test_decode.m` | kind by the first code statement, not by the presence of `function` |
| Packages (`+sn/+config`, `+sn/+limits`, `+sn/+report`, `+sn`) | `+sn/` | qualified names resolve (`sn.config.defaults`), `package` edges |
| Class folder and `classdef` | `@BatteryModel/`, `PacketStats.m` | methods declared in the class file are local names; `obj.method(...)` becomes a `method-name` edge (receiver type unknown, said so) |
| Private folder | `private/clamp.m` | resolves only from files in the parent folder |
| Dynamic dispatch | `dispatch_handler.m` (`str2func`, `eval`, `run`), `check_limits.m` (`feval`) | listed per file; a string *literal* naming a tree file becomes a `dynamic-literal` edge, computed arguments stay unresolved |
| Function handles | `run_soak.m` (`@on_violation`), `fit_battery_curve.m` (anonymous) | `@name` is a `handle` edge when it names a tree file; anonymous functions are ignored |
| Toolbox dependencies | `filter_fir.m` (`fir1`, `freqz`), `fit_battery_curve.m` (`lsqcurvefit`) | `wrap` with the toolbox named |
| Shadowing a built-in | `legacy/max.m` | flagged on the defining file and on every caller; path order decides which runs |
| Unresolved third-party name | `load_recording.m` (`tdms_read`) | listed under `unresolved`, never invented |
| Graphics-only script | `plots/plot_soak.m` | `retain` (plotting is not migration work); its caller-workspace variables are listed |
| Unreferenced code | `legacy/old_decode.m`, `util/notes_only.m` | `orphans` in the dependency map |
| Comment and string edge cases | `util/notes_only.m` (block comments, `'` in strings, `...` continuation, transposes) | stripped before any name is read |
| Non-UTF-8 bytes and CRLF | `legacy/garbled.m` | decoded with replacement, noted in `notes`, still inventoried |
| Vectors beside a unit | `moving_avg_rt_vectors.csv` | `missing_inputs` omits `vectors` for `moving_avg_rt.m`; it is the first unit `/matlab-to-code` can prove |
| Tests | `tests/` | inventoried with `role = test`, excluded from the backlog, counted as evidence for what they call |

`expected/m-fleet.json` and `expected/m-fleet-inventory.csv` are what `python tools/m_fleet_scan.py --check`
compares against. After a deliberate change to the fixture or the scanner run
`python tools/m_fleet_scan.py --check --write-expected` once and review the diff.
