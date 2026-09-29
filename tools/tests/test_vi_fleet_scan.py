"""Tests for tools/vi_fleet_scan.py. Run: python -m unittest tools/tests/test_vi_fleet_scan.py -q

A fake `lvkit` (a Python script) stands in for the real reader so the classification, CSV, backlog, and
failure-isolation paths run everywhere; the real reader is exercised by --check when it is installed.
"""

import csv
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import tracker_report  # noqa: E402
import vi_fleet_scan as fleet  # noqa: E402

FAKE_LVKIT = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("lvkit 0.0-fake"); sys.exit(0)
cmd = args[0]
path = args[-1]
name = path.rsplit("/", 1)[-1]
def inst(q):
    return {"kind": "instance", "qualified_name": q}
def scope(kind, *body):
    return {"kind": "scope", "scope_kind": kind, "frames": [{"body": list(body)}]}
if cmd == "describe":
    if "bad" in name:
        print("pylabview extraction failed: Could not read RSRC 0 Header", file=sys.stderr); sys.exit(1)
    body = {
        "Acquire.vi": [scope("while", inst("DAQmx Timing (Sample Clock).vi"), inst("DAQmx Read.vi"))],
        "Meter.vi": [inst("VISA Write.vi"), inst("VISA Read.vi"), inst("Scan From String")],
        "Limits.vi": [scope("case", inst("Greater?"), scope("for", inst("Add"))), inst("Format Into String")],
        "Sum.vi": [inst("Add"), inst("Add")],
        "Locked.vi": [inst("Add")],
    }.get(name, [inst("Add")])
    out = {"vi": path, "inputs": [{"name": "x", "type": "DBL"}], "outputs": [{"name": "y", "type": "DBL"}],
           "body": body, "class_context": None,
           "properties": {"lv_version": "20.0", "lock_state": "password_protected" if name == "Locked.vi" else "unlocked",
                          "kind": {"has_no_block_diagram": False}},
           "health": {"bad_node": name == "Limits.vi", "is_broken": name == "Limits.vi"}}
    print(json.dumps(out))
elif cmd == "unresolved":
    if "bad" in name:
        sys.exit(1)
    print(json.dumps([{"kind": "unknown_primitive", "identifier": "1503", "name": "String Subset", "count": 1}] if name == "Limits.vi" else []))
elif cmd == "index":
    print(json.dumps({"vis": 5, "collisions": 0, "ms": 1}))
elif cmd == "query":
    print(json.dumps({"columns": ["path", "callers_count", "impact_score"],
                      "rows": [["rig/Sum.vi", 3, 4], ["rig/Limits.vi", 1, 1]]}))
else:
    sys.exit(2)
'''

LVPROJ = """<?xml version='1.0' encoding='UTF-8'?>
<Project Type="Project" LVVersion="20008000">
  <Item Name="My Computer" Type="My Computer">
    <Item Name="Sum.vi" Type="VI" URL="rig/Sum.vi"/>
    <Item Name="Limits.vi" Type="VI" URL="rig/Limits.vi"/>
    <Item Name="Elsewhere.vi" Type="VI" URL="../../elsewhere/Elsewhere.vi"/>
    <Item Name="Dependencies" Type="Dependencies"/>
  </Item>
  <Item Name="RT Target" Type="RT CompactRIO">
    <Item Name="Control.vi" Type="VI" URL="rt/Control.vi"/>
  </Item>
</Project>
"""
SEQ_INI = "[Sequence MainSequence]\nStep0.Module.VIPath = C:\\rigs\\rig\\Sum.vi\nStep1.Module.VIPath = rig\\Meter.vi\n"


class FleetScanTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self.tree = self.dir / "fleet"
        for rel in ("rig/Acquire.vi", "rig/Meter.vi", "rig/Limits.vi", "rig/Sum.vi", "rig/Locked.vi", "rig/bad.vi", "rt/Control.vi"):
            p = self.tree / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"RSRC" + rel.encode())
        (self.tree / "rig" / "Sum.csv").write_text("x,y\n1,1\n", encoding="utf-8")
        (self.tree / "fleet.lvproj").write_text(LVPROJ, encoding="utf-8")
        (self.tree / "bench.seq").write_text(SEQ_INI, encoding="utf-8")
        (self.tree / "binary.seq").write_bytes(b"\x00\x01TSBIN\x02")
        fake = self.dir / "lvkit"
        fake.write_text(FAKE_LVKIT, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.fake = str(fake)
        self.original_which = fleet.lvkit_path

    def tearDown(self):
        fleet.lvkit_path = self.original_which
        self.td.cleanup()

    def scan(self, exe):
        fleet.lvkit_path = lambda: exe
        result = fleet.scan_tree(self.tree)
        paths = fleet.write_outputs(result, self.dir / "out", "fleet", 50, "VI", "2026-01-05")
        rows = list(csv.DictReader(io.StringIO(paths["inventory"].read_text(encoding="utf-8"))))
        return result, paths, {r["name"]: r for r in rows}

    def test_fake_lvkit_classifies_and_isolates_failures(self):
        result, paths, by = self.scan(self.fake)
        self.assertEqual(result["summary"]["reader"], "lvkit 0.0-fake")
        self.assertEqual(by["Acquire.vi"]["classification"], "retain")
        self.assertIn("DAQmx hardware timing", by["Acquire.vi"]["reasons"])
        self.assertEqual(by["Control.vi"]["classification"], "retain")
        self.assertIn("RT Target [RT CompactRIO]", by["Control.vi"]["target"])
        self.assertEqual(by["Meter.vi"]["classification"], "wrap")
        self.assertIn("VISA", by["Meter.vi"]["reasons"])
        self.assertEqual(by["Sum.vi"]["classification"], "port")
        self.assertEqual(by["Limits.vi"]["classification"], "port")
        self.assertIn("unresolved primitive", by["Limits.vi"]["reasons"])
        self.assertIn("bad_node", by["Limits.vi"]["health"])
        self.assertEqual(by["bad.vi"]["classification"], "unreadable")
        self.assertIn("RSRC", by["bad.vi"]["reasons"])
        self.assertEqual(by["Locked.vi"]["classification"], "unreadable")
        self.assertIn("password", by["Locked.vi"]["reasons"])
        self.assertEqual(by["Limits.vi"]["structures"], "case:1;for:1")
        self.assertEqual(by["Limits.vi"]["max_nesting"], "2")
        self.assertEqual(by["Limits.vi"]["unresolved"], "unknown_primitive:String Subset(1503)")
        self.assertEqual(by["Sum.vi"]["callers_count"], "3")
        self.assertEqual(by["Sum.vi"]["sequences"], "bench.seq")
        self.assertNotIn("recording", by["Sum.vi"]["missing_inputs"])
        self.assertIn("recording", by["Meter.vi"]["missing_inputs"])
        self.assertEqual(result["summary"]["classification"], {"port": 2, "wrap": 1, "retain": 2, "unreadable": 2})
        self.assertEqual(result["summary"]["projects"][0]["vis_outside_tree"], 1)
        formats = {s["file"]: s["format"] for s in result["summary"]["sequences"]}
        self.assertEqual(formats, {"bench.seq": "ini", "binary.seq": "binary"})

    def test_complexity_and_priority_are_reproducible(self):
        facts = {"primitives": ["a", "b"], "structures": {"case": 1}, "subvis": ["x.vi"], "unresolved": ["u"], "max_nesting": 2, "terminals": 3}
        self.assertEqual(fleet.complexity(facts), 2 + 2 + 3 + 5 + 4 + 3)
        self.assertEqual(fleet.priority(3, ["recording"], 10), 100 + 30 + 10 - 10)
        self.assertEqual(fleet.priority(None, [], 200), 100 + 30 - 60)

    def test_outputs_are_deterministic_and_tracker_compatible(self):
        _, paths, by = self.scan(self.fake)
        first = paths["inventory"].read_text(encoding="utf-8")
        self.assertEqual(first.splitlines()[0], ",".join(fleet.COLUMNS))
        self.assertEqual([r["path"] for r in csv.DictReader(io.StringIO(first))], sorted(r["path"] for r in by.values()))
        items = tracker_report.load(paths["backlog"])
        self.assertEqual([i["id"] for i in items], ["VI-CAP-001", "VI-CAP-002", "VI-CAP-003"])
        self.assertTrue(items[0]["title"].startswith("Port "))
        self.assertEqual(items[-1]["title"], "Wrap Meter.vi")
        with paths["backlog_csv"].open(encoding="utf-8") as f:
            self.assertEqual(csv.DictReader(f).fieldnames, fleet.BACKLOG_COLUMNS)
        _, paths2, _ = self.scan(self.fake)
        self.assertEqual(first, paths2["inventory"].read_text(encoding="utf-8"))

    def test_without_lvkit_rows_still_appear(self):
        result, paths, by = self.scan(None)
        self.assertEqual(result["summary"]["reader"], fleet.ABSENT)
        self.assertTrue(any(fleet.ABSENT in n for n in result["summary"]["notes"]))
        self.assertEqual(len(by), 7)
        self.assertEqual(by["Sum.vi"]["classification"], "unreadable")
        self.assertIn(fleet.ABSENT, by["Sum.vi"]["reasons"])
        self.assertEqual(by["Control.vi"]["classification"], "retain")
        self.assertEqual(by["Sum.vi"]["reader"], fleet.ABSENT)
        self.assertEqual(json.loads(paths["backlog"].read_text(encoding="utf-8"))["items"], [])

    def test_bad_prefix_and_missing_tree(self):
        with self.assertRaises(SystemExit):
            fleet.build_backlog([], 5, "vi", "2026-01-05")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = fleet.main([str(self.dir / "nope")])
        self.assertEqual(code, 2)

    def test_check_passes_on_fixture(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = fleet.main(["--check"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("fleet check ok", out.getvalue())


if __name__ == "__main__":
    unittest.main()
