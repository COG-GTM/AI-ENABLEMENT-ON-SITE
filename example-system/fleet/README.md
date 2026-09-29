# Fleet-discovery fixture

Offline sample input for `/vi-fleet-discovery` and `tools/vi_fleet_scan.py`. The tree the scanner reads is
`example-system/` as a whole; this folder adds the project-level files around the four real VIs in
`../real-vi/` (public open-source, 0BSD, provenance and hashes in `../real-vi/sources.json`). No new binaries.

| File | What it is |
| --- | --- |
| `fleet.lvproj` | Synthetic LabVIEW project file (XML, hand-written). Lists the four VIs under `My Computer` and shows an `RT CompactRIO` target with an `FPGA Target` whose VI items point at files that do not exist, so the scanner's project-target handling and "missing member" count are exercised without inventing binaries |
| `bench-sequence.seq` | Synthetic TestStand-style sequence in the XML file format (hand-written stand-in for shape only). Names two of the VIs so the `sequences` column has something to show. Real sequence files are binary by default; the scanner lists those with the conversion note instead of parsing them |
| `expected/fleet.json` | What `python tools/vi_fleet_scan.py --check` expects: counts, backlog settings, the lvkit version the CSVs were produced with |
| `expected/fleet-inventory.lvkit.csv` | The inventory the scanner wrote for this tree with lvkit 0.8.4 installed |
| `expected/fleet-inventory.nolvkit.csv` | The same run without lvkit: every row present, `reader = lvkit absent` |

`--check` scans the tree into a temporary folder and compares it with the CSV that matches the reader on this
machine (structure only when a different lvkit version is installed). After a deliberate change run
`python tools/vi_fleet_scan.py --check --write-expected` once with lvkit and once without, and review the diff.
