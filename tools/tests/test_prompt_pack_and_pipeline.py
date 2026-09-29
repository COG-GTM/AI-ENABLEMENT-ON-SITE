"""tools/prompt_pack.py and tools/pipeline_run.py over the synthetic firmware-repo fixture (and the MATLAB/LabVIEW maps for
language detection): pack sections and ordering, budget shrinking, dry-run honesty, resume, external agent/compare commands,
and the tracker-shaped backlog-status file."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import prompt_pack  # noqa: E402
import pipeline_run  # noqa: E402

FW = ROOT / "example-system" / "firmware-repo"
PY = sys.executable

FAKE_AGENT = '''
import json, sys, pathlib
pack, results, pid, unit = sys.argv[1:5]
r = pathlib.Path(results); r.mkdir(parents=True, exist_ok=True)
text = pathlib.Path(pack).read_text(encoding="utf-8")
assert "## 3. Contract" in text and pid in text
if unit.endswith("median.c"):
    (r / "proof.txt").write_text("ok\\n")
    json.dump({"id": pid, "unit": unit, "status": "done", "target": "c", "evidence": ["proof.txt"], "notes": "fake"}, open(r / "result.json", "w"))
elif unit.endswith("fixed_point.h"):
    json.dump({"id": pid, "unit": unit, "status": "done", "target": "c", "evidence": [], "notes": "no evidence"}, open(r / "result.json", "w"))
else:
    json.dump({"id": pid, "unit": unit, "status": "blocked", "blocked_on": "vectors", "evidence": [], "notes": "fake"}, open(r / "result.json", "w"))
'''


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], capture_output=True, text=True, cwd=cwd)


class ScanOnce(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.scan = cls.tmp / "scan"
        r = run("tools/c_fleet_scan.py", str(FW), "--name", "fw", "--out-dir", str(cls.scan), "--opened", "2026-01-05", "--no-gcc")
        assert r.returncode == 0, r.stderr
        cls.map = cls.scan / "fw-c-dependency-map.json"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)


class PromptPackTests(ScanOnce):
    def packs(self, *extra: str) -> tuple[Path, dict]:
        out = self.tmp / ("packs-" + str(abs(hash(extra)) % 10_000))
        r = run("tools/prompt_pack.py", "--map", str(self.map), "--out-dir", str(out), "--json", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out, json.loads(r.stdout)

    def test_detects_language_from_map_keys(self) -> None:
        self.assertEqual(prompt_pack.detect_language({"toolboxes": {}}), "matlab")
        self.assertEqual(prompt_pack.detect_language({"projects": [], "nodes": []}), "labview")
        self.assertEqual(prompt_pack.detect_language({"include_check": {}}), "c")
        with self.assertRaises(SystemExit):
            prompt_pack.detect_language({"nodes": []})

    def test_one_pack_per_backlog_unit_in_leaf_first_order_with_tracker_ids(self) -> None:
        out, man = self.packs()
        backlog = json.loads((self.scan / "fw-c-migration-backlog.json").read_text())
        self.assertEqual(man["totals"]["packs"], len(backlog["items"]))
        ids = [p["id"] for p in man["packs"]]
        self.assertEqual(sorted(ids), sorted(i["id"] for i in backlog["items"]))
        dep_map = json.loads(self.map.read_text())
        pos = {p: i for i, p in enumerate(dep_map["leaf_first_order"])}
        units = [p["unit"] for p in man["packs"]]
        self.assertEqual(units, sorted(units, key=lambda u: pos[u]))
        self.assertTrue((out / "INDEX.md").is_file() and (out / "manifest.json").is_file())
        self.assertEqual(sorted(x.name for x in out.glob("*.md") if x.name != "INDEX.md"), sorted(f"{i}.md" for i in ids))
        self.assertIn("tokens", man["_about"])
        self.assertGreater(man["whole_tree"]["tokens_est"], 0)

    def test_pack_sections_and_facts(self) -> None:
        out, man = self.packs()
        spi = next(p for p in man["packs"] if p["unit"] == "drivers/spi_driver.c")
        text = (ROOT / spi["file"]).read_text(encoding="utf-8") if not Path(spi["file"]).is_absolute() else Path(spi["file"]).read_text(encoding="utf-8")
        for h in ("## 1. Unit", "## 2. Task", "## 3. Contract", "## 4. Source", "## 5. Dependencies", "## 6. Callers", "## 7. Open questions", "## 8. Boundaries"):
            self.assertIn(h, text)
        self.assertLess(text.index("## 1. Unit"), text.index("## 2. Task"))
        self.assertLess(text.index("## 5. Dependencies"), text.index("## 6. Callers"))
        self.assertIn("classification: **wrap**", text)
        self.assertIn("int spi_transfer(", text)                         # own source included
        self.assertIn("`drivers/hal_gpio.c` [call] wrap, uses: `hal_gpio_write`", text)
        self.assertIn("void hal_gpio_write(int pin, bool level)", text)  # dependency excerpt
        self.assertIn("`app/main.c`", text)                              # caller
        self.assertIn(f"results/{spi['id']}/result.json", text)
        self.assertIn("bring-your-firmware", text)
        self.assertIn("did not run, compile", text)
        self.assertIn("drivers/hal_gpio.c", spi["dependencies"])
        self.assertTrue(spi["source_included"])

    def test_labview_pack_uses_node_record_and_lvkit_commands(self) -> None:
        tmp_scan = self.tmp / "lv"
        r = run("tools/vi_fleet_scan.py", str(ROOT / "example-system"), "--name", "fleet", "--out-dir", str(tmp_scan), "--opened", "2026-01-05")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.tmp / "lvpacks"
        # --all: without lvkit every VI is unreadable and the backlog is empty, so pack every node
        r = run("tools/prompt_pack.py", "--map", str(tmp_scan / "fleet-dependency-map.json"), "--out-dir", str(out), "--json", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        man = json.loads(r.stdout)
        self.assertEqual(man["language"], "labview")
        self.assertEqual(man["totals"]["packs"], 4)
        text = Path(man["packs"][0]["file"]).read_text(encoding="utf-8") if Path(man["packs"][0]["file"]).is_absolute() else (ROOT / man["packs"][0]["file"]).read_text(encoding="utf-8")
        self.assertIn("Binary VI: no text source", text)
        self.assertIn("lvkit describe --format json --no-auto-vilib", text)
        self.assertIn("labview-to-python", text)
        self.assertFalse(man["packs"][0]["source_included"])

    def test_budget_shrinks_dependencies_then_source(self) -> None:
        out, man = self.packs("--budget", "150")
        spi = next(p for p in man["packs"] if p["unit"] == "drivers/spi_driver.c")
        self.assertTrue(spi["truncated"], spi)
        self.assertTrue(any("dependency excerpts" in t for t in spi["truncated"]))
        self.assertTrue(spi["source_cut"])
        text = Path(spi["file"]).read_text(encoding="utf-8") if Path(spi["file"]).is_absolute() else (ROOT / spi["file"]).read_text(encoding="utf-8")
        self.assertIn("bytes cut to fit the budget", text)
        for h in ("## 3. Contract", "## 6. Callers", "## 8. Boundaries"):
            self.assertIn(h, text)                                        # fixed sections never cut
        self.assertGreater(man["totals"]["truncated"], 0)

    def test_all_units_and_single_unit_and_task_file(self) -> None:
        _, man_all = self.packs("--all")
        self.assertEqual(man_all["totals"]["packs"], len(json.loads(self.map.read_text())["nodes"]))
        self.assertTrue(any(p["id"].startswith("UNIT-") for p in man_all["packs"]))   # non-backlog units get UNIT ids
        task = self.tmp / "task.md"
        task.write_text("CUSTOM TASK TEXT\n", encoding="utf-8")
        out, man = self.packs("--unit", "algo/pid.c", "--task-file", str(task))
        self.assertEqual([p["unit"] for p in man["packs"]], ["algo/pid.c"])
        text = Path(man["packs"][0]["file"]).read_text(encoding="utf-8") if Path(man["packs"][0]["file"]).is_absolute() else (ROOT / man["packs"][0]["file"]).read_text(encoding="utf-8")
        self.assertIn("CUSTOM TASK TEXT", text)
        r = run("tools/prompt_pack.py", "--map", str(self.map), "--out-dir", str(out), "--unit", "nope.c")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in the map", r.stderr)

    def test_deterministic_bytes(self) -> None:
        out1, _ = self.packs("--name", "det")
        b1 = {p.name: p.read_bytes() for p in out1.glob("*")}
        r = run("tools/prompt_pack.py", "--map", str(self.map), "--out-dir", str(out1), "--name", "det")
        self.assertEqual(r.returncode, 0, r.stderr)
        b2 = {p.name: p.read_bytes() for p in out1.glob("*")}
        self.assertEqual(b1, b2)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "pipe"
        self.agent = self.tmp / "fake_agent.py"
        self.agent.write_text(FAKE_AGENT, encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def base(self, *extra: str) -> subprocess.CompletedProcess:
        return run("tools/pipeline_run.py", "--lang", "c", "--tree", str(FW), "--name", "fw", "--out", str(self.out), "--opened", "2026-01-05", *extra)

    def journal(self) -> list[dict]:
        return [json.loads(l) for l in (self.out / "journal.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_dry_run_writes_no_results_and_says_so(self) -> None:
        r = self.base("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(r.stdout)
        self.assertEqual(sorted(state["stages"]), sorted(pipeline_run.STAGES))
        self.assertEqual(state["stages"]["agent"]["mode"], "dry run")
        self.assertTrue(all(u["status"] == "skipped" for u in state["stages"]["agent"]["units"].values()))
        self.assertFalse((self.out / "results").exists())
        report = (self.out / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("Agent stage mode: **dry run**", report)
        self.assertIn("15 skipped (dry run)", report)
        self.assertIn("0 units with a passing comparison", report)
        status = json.loads((self.out / "fw-backlog-status.json").read_text())
        self.assertTrue(all(i["status"] == "proposed" for i in status["items"]))
        self.assertIn("0 moved to in_review", status["_about"])
        self.assertTrue((self.out / "scan" / "fw-c-dependency-map.json").is_file())
        self.assertTrue((self.out / "packs" / "manifest.json").is_file())
        events = self.journal()
        self.assertEqual(events[0]["stage"], "scan")
        self.assertTrue(any(e["event"] == "skipped" and "dry run" in e.get("reason", "") for e in events))

    def test_resume_skips_unchanged_stages_and_from_stage_forces(self) -> None:
        self.assertEqual(self.base().returncode, 0)
        n = len(self.journal())
        r = self.base("--resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        new = self.journal()[n:]
        skipped = [e for e in new if e["event"] == "skipped" and "--resume" in e.get("reason", "")]
        self.assertEqual({e["stage"] for e in skipped}, {"scan", "pack"})
        n = len(self.journal())
        r = self.base("--resume", "--from-stage", "pack", "--until", "pack")
        self.assertEqual(r.returncode, 0, r.stderr)
        new = self.journal()[n:]
        self.assertTrue(any(e["stage"] == "pack" and e["event"] == "start" for e in new))
        self.assertFalse(any(e["stage"] == "agent" for e in new))

    def test_agent_and_compare_commands_and_backlog_status(self) -> None:
        r = self.base("--agent-cmd", f"{PY} {self.agent} {{pack}} {{results}} {{id}} {{unit}}", "--limit", "3", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(r.stdout)
        units = state["stages"]["agent"]["units"]
        self.assertEqual(sum(1 for u in units.values() if u["status"] != "skipped"), 3)
        comp = state["stages"]["compare"]["units"]
        done_ok = [k for k, v in comp.items() if v["status"] == "evidence present"]
        unproven = [k for k, v in comp.items() if v["status"] == "unproven"]
        blocked = [k for k, v in comp.items() if v["status"] == "blocked"]
        self.assertEqual(len(done_ok), 1)
        self.assertEqual(len(unproven), 1)     # done without evidence is not proof
        self.assertEqual(len(blocked), 1)
        status = json.loads((self.out / "fw-backlog-status.json").read_text())
        moved = [i for i in status["items"] if i["status"] == "in_review"]
        self.assertEqual([i["id"] for i in moved], done_ok)
        self.assertIn("1 moved to in_review", status["_about"])
        r2 = run("tools/tracker_report.py", "--file", str(self.out / "fw-backlog-status.json"))
        self.assertEqual(r2.returncode, 0, r2.stderr)
        # a second pass keeps existing results and runs the agent on the rest, then an external compare decides proof
        cmp_script = self.tmp / "cmp.py"
        cmp_script.write_text("import sys; sys.exit(0 if sys.argv[2].endswith('median.c') else 1)\n", encoding="utf-8")
        r = self.base("--resume", "--agent-cmd", f"{PY} {self.agent} {{pack}} {{results}} {{id}} {{unit}}",
                      "--compare-cmd", f"{PY} {cmp_script} {{id}} {{unit}}", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(r.stdout)
        self.assertEqual({u.get("source") for u in state["stages"]["agent"]["units"].values() if u.get("source")}, {"existing result.json"})
        self.assertEqual(sum(1 for u in state["stages"]["agent"]["units"].values() if u["status"] == "skipped"), 0)
        comp = state["stages"]["compare"]["units"]
        self.assertEqual([k for k, v in comp.items() if v["status"] == "proven"], done_ok)
        self.assertTrue(any(v["status"] == "failed" for v in comp.values()))   # fixed_point.h: done but compare exit 1
        self.assertTrue((self.out / "results" / done_ok[0] / "compare-output.txt").is_file())

    def test_agent_without_result_json_is_failed_not_done(self) -> None:
        r = self.base("--agent-cmd", "true", "--limit", "1", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(r.stdout)
        self.assertEqual([u["status"] for u in state["stages"]["agent"]["units"].values() if u["status"] != "skipped"], ["failed"])
        self.assertTrue(any(e["event"] == "no result.json" for e in self.journal()))

    def test_bad_tree_and_failed_scan_are_reported(self) -> None:
        r = run("tools/pipeline_run.py", "--lang", "c", "--tree", str(self.tmp / "missing"), "--name", "x", "--out", str(self.out))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a directory", r.stderr)


if __name__ == "__main__":
    unittest.main()
