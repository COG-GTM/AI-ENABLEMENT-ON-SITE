# Manual-review report: `Thermal Soak Test.vi` → `rig.py`

What `/labview-to-python` leaves behind next to the Python file. Numbers here come from
`bench_compare.py`, not from reading the code.

## Inputs used

| Evidence | File | What it gave us |
| --- | --- | --- |
| LabVIEW HTML export (File > Print > HTML) | `rig.vi.html` | connector pane, controls/indicators, diagram structure, subVI list |
| Raw sample log from the rig | `rig_samples.csv` | 24 packets (3 setpoints x 8), with timestamps |
| Results the rig recorded | `rig_recording.csv` | the 3 result rows the port must reproduce |
| Direct `.vi` parse (`lvkit describe`) | not available for this synthetic rig | would have added the wiring graph and broken-node list |

## Behaviour reproduced, and proven by replay

```bash
python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv
python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv
```

All 9 columns PASS, exact tolerance, 3 of 3 rows. Rounding is the part that would have failed
silently: LabVIEW's **Round To Nearest** sends x.5 to the even integer; step 1 (`2500.5 → 2500`)
and step 2 (`5023.5 → 5024`) exercise both directions. Python's `round()` matches; a C-style
`(int)(x + 0.5)` would not.

## Behaviour NOT reproduced: review on the bench before retiring the VI

| VI element | Why it is not in `rig.py` | What to do |
| --- | --- | --- |
| `Wait (ms)` settle time (120 s default) | replay has no time axis; timing correctness is not checkable from a CSV | keep the wait in live mode; confirm the chamber's own settle criterion, not just a delay |
| `Chamber Set Temp.vi` (VISA serial `SET <degC>`) | hardware protocol; not exercised offline | implement `set_chamber` with pyvisa/pyserial and test against the chamber or its simulator |
| `Read Node Packet.vi` frame sync + CRC | replay starts from decoded samples | reuse `example-system/sim/sensor_node/packet.py` (same frame, same CRC) for live reads |
| Error cluster: skipped step, no row logged | replay data has no error path recorded | decide whether the port should log a FAIL row instead; that is a behaviour change to agree on |
| `Chamber temp (degC)` live indicator | display only, never logged | drop, or expose as a log line |
| Cleanup frame (chamber back to 25, VISA Close) | no hardware offline | keep in live mode; run under `try/finally` |

## Recommendation: **port**, keep the VI until one live run matches

- The logic is small, fully understood from the export, and verified against the recording.
- Two live runs are needed before the VI is retired: one PASS-only run and one with a forced FAIL
  (or a disconnected node) to see the error path.
- If the team later needs the FPGA- or RT-hosted variant of this rig, that part stays in LabVIEW and
  Python **wraps** it (calls the built executable / reads its output file); do not port it.
