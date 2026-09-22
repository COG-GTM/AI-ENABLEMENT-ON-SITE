"""Tests for tools/trace_matrix.py and tools/golden_path.py. Run: python -m unittest discover -s tools/tests -q"""

import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import golden_path  # noqa: E402
import trace_matrix  # noqa: E402

SYSTEM = ROOT / "example-system"


def make_system(tmp: Path, srs: str, hazards: str, tests: dict[str, str], tracker: list[dict]) -> Path:
    sysdir = tmp / "sys"
    (sysdir / "docs").mkdir(parents=True)
    (sysdir / "tests").mkdir()
    (sysdir / "docs" / "SRS.md").write_text(srs, encoding="utf-8")
    (sysdir / "docs" / "HAZARDS.md").write_text(hazards, encoding="utf-8")
    (sysdir / "docs" / "BUDGET.md").write_text("# Budget\n", encoding="utf-8")
    for name, body in tests.items():
        (sysdir / "tests" / name).write_text(body, encoding="utf-8")
    (sysdir / "tracker.json").write_text(json.dumps({"items": tracker}), encoding="utf-8")
    return sysdir


SRS = """# SRS

| ID | Requirement | Priority | Verified by |
| --- | --- | --- | --- |
| XX-REQ-001 | Sample at 100 Hz. | Must | `test_rate` |
| XX-REQ-002 | Fit the power budget. | Must | `BUDGET.md` review |
"""
HAZARDS = """# Hazards

| ID | Failure mode | Effect | Sev | Lik | Risk | Mitigation | Verified by | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| XX-HAZ-001 | Sensor stalls | Stale data | 3 | 3 | 9 | Watchdog (XX-REQ-001) | `test_rate` | Mitigated |
"""
TESTS = {"test_node.py": "def test_rate(self):  # XX-REQ-001\n    pass\n",
         "test_fw.c": "static void test_rate(void) { /* XX-REQ-001 */ }\n"}


class TraceMatrixTests(unittest.TestCase):
    def test_example_system_is_fully_traced(self):
        m = trace_matrix.build(SYSTEM)
        self.assertEqual(m["problems"], [])
        c = m["counts"]
        self.assertEqual(c["untested"], 0)
        self.assertEqual(c["tested"] + c["analysis"], c["requirements"])

    def test_counts_match_source_files_both_ways(self):
        m = trace_matrix.build(SYSTEM)
        srs_ids = set(re.findall(r"^\|\s*(SN-REQ-\d{3})\s*\|", (SYSTEM / "docs" / "SRS.md").read_text(), re.M))
        haz_ids = set(re.findall(r"^\|\s*(SN-HAZ-\d{3})\s*\|", (SYSTEM / "docs" / "HAZARDS.md").read_text(), re.M))
        tracker = json.loads((SYSTEM / "tracker.json").read_text())["items"]
        self.assertEqual({r["id"] for r in m["requirements"]}, srs_ids)
        self.assertEqual({h["id"] for h in m["hazards"]}, haz_ids)
        self.assertEqual(m["counts"]["tracker_items"], len(tracker))
        # every tracker link lands on a real requirement/hazard and is recorded on it
        for it in tracker:
            for rid in it.get("requirements", []):
                self.assertIn(it["id"], next(r for r in m["requirements"] if r["id"] == rid)["tracker"])
            for hid in it.get("hazards", []):
                self.assertIn(it["id"], next(h for h in m["hazards"] if h["id"] == hid)["tracker"])

    def test_every_named_test_in_srs_exists(self):
        _, names = trace_matrix.scan_tests(SYSTEM / "tests")
        for r in trace_matrix.read_requirements(SYSTEM / "docs" / "SRS.md").values():
            for name in trace_matrix.NAMED_TEST_RE.findall(r["verified_by"]):
                self.assertIn(name, names, r["id"])

    def test_minimal_system_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sysdir = make_system(Path(tmp), SRS, HAZARDS, TESTS, [])
            m = trace_matrix.build(sysdir)
        self.assertEqual(m["problems"], [])
        self.assertEqual(m["counts"], {"requirements": 2, "hazards": 1, "tracker_items": 0, "tested": 2 - 1, "analysis": 1, "untested": 0})
        r1 = next(r for r in m["requirements"] if r["id"] == "XX-REQ-001")
        self.assertEqual(r1["verdict"], "tested")
        self.assertEqual(r1["hazards"], ["XX-HAZ-001"])
        self.assertEqual(r1["tests"], {"python": ["tests/test_node.py::test_rate"], "c": ["tests/test_fw.c::test_rate"]})

    def test_columns_are_found_by_header_not_position(self):
        srs = SRS.replace("| ID | Requirement | Priority | Verified by |", "| ID | Verified by | Owner | Requirement | Priority |") \
                 .replace("| XX-REQ-001 | Sample at 100 Hz. | Must | `test_rate` |", "| XX-REQ-001 | `test_rate` | fw team | Sample at 100 Hz. | Must |") \
                 .replace("| XX-REQ-002 | Fit the power budget. | Must | `BUDGET.md` review |", "| XX-REQ-002 | `BUDGET.md` review | pwr team | Fit the power budget. | Should |") \
                 .replace("| --- | --- | --- | --- |", "| --- | --- | --- | --- | --- |")
        haz = HAZARDS.replace("| ID | Failure mode | Effect | Sev | Lik | Risk | Mitigation | Verified by | Status |",
                              "| ID | Status | Risk | Mitigation | Failure mode |") \
                     .replace("| --- | --- | --- | --- | --- | --- | --- | --- | --- |", "| --- | --- | --- | --- | --- |") \
                     .replace("| XX-HAZ-001 | Sensor stalls | Stale data | 3 | 3 | 9 | Watchdog (XX-REQ-001) | `test_rate` | Mitigated |",
                              "| XX-HAZ-001 | Mitigated | 9 | Watchdog (XX-REQ-001) | Sensor stalls |")
        with tempfile.TemporaryDirectory() as tmp:
            m = trace_matrix.build(make_system(Path(tmp), srs, haz, TESTS, []))
        self.assertEqual(m["problems"], [])
        r2 = next(r for r in m["requirements"] if r["id"] == "XX-REQ-002")
        self.assertEqual((r2["priority"], r2["verdict"]), ("Should", "analysis"))
        h = m["hazards"][0]
        self.assertEqual((h["risk"], h["requirements"], h["status"], h["failure_mode"]), (9, ["XX-REQ-001"], "Mitigated", "Sensor stalls"))

    def test_rows_outside_a_table_are_ignored(self):
        srs = SRS + "\nProse mentioning | XX-REQ-009 | in passing | is not a row |\n"
        with tempfile.TemporaryDirectory() as tmp:
            m = trace_matrix.build(make_system(Path(tmp), srs, HAZARDS, TESTS, []))
        self.assertEqual({r["id"] for r in m["requirements"]}, {"XX-REQ-001", "XX-REQ-002"})

    def test_problems_are_reported(self):
        srs = SRS.replace("`BUDGET.md` review", "`test_missing`") + "| XX-REQ-003 | Never checked. | Could | nothing |\n"
        haz = HAZARDS + "| XX-HAZ-002 | Overheats | Fire | 4 | 3 | 12 | none yet | - | Open |\n"
        tests = dict(TESTS, **{"test_extra.py": "def test_ghost(self):  # XX-REQ-099\n    pass\n"})
        tracker = [{"id": "XX-BUG-001", "requirements": ["XX-REQ-050"], "hazards": ["XX-HAZ-050"]}]
        with tempfile.TemporaryDirectory() as tmp:
            m = trace_matrix.build(make_system(Path(tmp), srs, haz, tests, tracker))
        joined = "\n".join(m["problems"])
        for expected in ("XX-REQ-002 says verified by `test_missing` but no such test exists",
                         "XX-REQ-003 has no test and no analysis artifact",
                         "XX-HAZ-002 has risk 12 but no mitigation requirement",
                         "XX-HAZ-002 is Open but no tracker item references it",
                         "XX-REQ-099 appears in tests but not in SRS.md",
                         "XX-BUG-001 references XX-REQ-050 which is not in SRS.md",
                         "XX-BUG-001 references XX-HAZ-050 which is not in HAZARDS.md"):
            self.assertIn(expected, joined)
        self.assertEqual(m["counts"]["untested"], 2)  # REQ-002 (phantom test) and REQ-003

    def test_hazard_test_names_are_checked_including_qualified_form(self):
        good = HAZARDS.replace("| `test_rate` | Mitigated |", "| `test_node.test_rate`, C `test_rate` | Mitigated |")
        bad = HAZARDS.replace("| `test_rate` | Mitigated |", "| `test_missing`, `test_fw.test_rate`, `test_node.test_nope` | Mitigated |")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(trace_matrix.build(make_system(Path(tmp) / "good", SRS, good, TESTS, []))["problems"], [])
            m = trace_matrix.build(make_system(Path(tmp) / "bad", SRS, bad, TESTS, []))
        self.assertEqual(m["problems"], ["XX-HAZ-001 says verified by `test_missing` but no such test exists",
                                         "XX-HAZ-001 says verified by `test_node.test_nope` but no such test exists"])

    def test_named_analysis_artifact_must_exist(self):
        srs = SRS.replace("`BUDGET.md` review", "`MISSING.md` review")  # the hint word must not rescue a missing file
        haz = HAZARDS.replace("| `test_rate` | Mitigated |", "| GONE.md | Mitigated |")
        with tempfile.TemporaryDirectory() as tmp:
            m = trace_matrix.build(make_system(Path(tmp), srs, haz, TESTS, []))
            self.assertEqual(m["problems"], ["XX-REQ-002 says verified by MISSING.md but no such file exists",
                                             "XX-HAZ-001 says verified by GONE.md but no such file exists",
                                             "XX-REQ-002 has no test and no analysis artifact"])
            self.assertEqual([r["verdict"] for r in m["requirements"] if r["id"] == "XX-REQ-002"], ["UNTESTED"])
            self.assertEqual(m["counts"]["analysis"], 0)
            # a bare file name (no hint word) is enough once the file exists; docs/ and the system root both count
            sysdir = make_system(Path(tmp) / "b", SRS.replace("`BUDGET.md` review", "BUDGET.md, NOTES.md"), HAZARDS, TESTS, [])
            (sysdir / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
            m = trace_matrix.build(sysdir)
        self.assertEqual(m["problems"], [])
        r2 = next(r for r in m["requirements"] if r["id"] == "XX-REQ-002")
        self.assertEqual((r2["verdict"], r2["artifacts"]), ("analysis", ["BUDGET.md", "NOTES.md"]))
        self.assertEqual(trace_matrix.artifacts(sysdir, "../../etc/x.md"), ([], ["../../etc/x.md"]))

    def test_cli_exit_codes_and_markdown(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = trace_matrix.main([])
        self.assertEqual(code, 0)
        self.assertIn("| Requirement | Priority |", out.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            sysdir = make_system(Path(tmp), SRS + "| XX-REQ-003 | Never checked. | Could | nothing |\n", HAZARDS, TESTS, [])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = trace_matrix.main(["--system", str(sysdir), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("XX-REQ-003", json.loads(out.getvalue())["problems"][0])
            self.assertIn("problem:", err.getvalue())
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(trace_matrix.main(["--system", str(Path(tmp) / "nowhere")]), 1)


class GoldenPathTests(unittest.TestCase):
    def setUp(self):
        golden_path.results.clear()

    def test_every_stage_passes_here(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = golden_path.main(["--skip-tests", "--json"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        data = json.loads(out.getvalue())  # stdout is pure JSON; progress lines go to stderr
        self.assertIn("ok   doctor:", err.getvalue())
        self.assertTrue(data["ok"])
        stages = {s["stage"] for s in data["stages"]}
        self.assertEqual(stages, {"doctor", "research-brief", "what-if", "tracker", "trace-matrix", "exec-deck",
                                  "exec-deck-pptx", "spec-example", "mcp-server", "model-to-code",
                                  "labview-to-python", "host-harness"})
        report = (golden_path.OUT / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn(f"{len(stages)}/{len(stages)} stages passed", report)
        for name in ("brief.md", "brief.html", "what-if-baseline.md", "what-if-imu-c-can.md", "status.md",
                     "trace-matrix.md", "deck.html", "mcp-handshake.jsonl", "model-python.csv", "model-compare.md",
                     "rig-python.csv", "rig-compare.md"):
            self.assertTrue((golden_path.OUT / name).exists(), name)

    def test_docs_quote_the_counts_the_stages_measure(self):
        # README and the three skills quote sizes of the example lanes; pin them to the files and stage output.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            golden_path.stage_model()
            golden_path.stage_bench()
            golden_path.stage_host_harness()
        detail = {r["stage"]: r["detail"] for r in golden_path.results}
        vectors = len((SYSTEM / "model" / "filter_vectors.csv").read_text(encoding="utf-8").splitlines()) - 1
        samples = len((SYSTEM / "bench" / "rig_samples.csv").read_text(encoding="utf-8").splitlines()) - 1
        recording = (SYSTEM / "bench" / "rig_recording.csv").read_text(encoding="utf-8").splitlines()
        steps, columns = len(recording) - 1, len(recording[0].split(","))
        self.assertIn(f"{vectors} vectors", detail["model-to-code"])
        self.assertIn(f"{steps} soak steps", detail["labview-to-python"])
        self.assertIn(f"{columns}/{columns} columns", detail["labview-to-python"])
        docs = {p: (ROOT / p).read_text(encoding="utf-8") for p in (
            "README.md", ".devin/skills/matlab-to-code/SKILL.md", ".devin/skills/labview-to-python/SKILL.md",
            "example-system/model/MODEL-NOTES.md", "example-system/bench/RIG-REVIEW.md")}
        self.assertIn(f"{vectors} rows", docs["README.md"])
        self.assertIn(f"{vectors} rows", docs["example-system/model/MODEL-NOTES.md"])
        self.assertIn(f"{vectors} vectors", docs[".devin/skills/matlab-to-code/SKILL.md"])
        self.assertIn(f"{samples} raw readings", docs["README.md"])
        self.assertIn(f"{samples} packets", docs["example-system/bench/RIG-REVIEW.md"])
        self.assertIn(f"{samples} samples into {steps} step", docs[".devin/skills/labview-to-python/SKILL.md"])
        self.assertIn(f"{columns} of {columns} columns", docs["README.md"])
        self.assertIn(f"{columns}/{columns} columns", docs[".devin/skills/labview-to-python/SKILL.md"])
        m = re.search(r"(\d+) checks against", detail["host-harness"])
        if m:  # only when a C compiler ran the harness
            checks = m.group(1)
            self.assertEqual(docs["README.md"].count(f"{checks} checks"), 2)
            self.assertIn(f"{checks} checks pass", (ROOT / ".devin/skills/bring-your-firmware/SKILL.md").read_text(encoding="utf-8"))

    def test_doctor_failures_are_named(self):
        original = golden_path.run
        fake = json.dumps({"ready": False, "checks": [{"check": "Python", "status": "OK", "detail": ""},
                                                        {"check": "outputs/ writable", "status": "FAIL", "detail": "x"}]})
        golden_path.run = lambda cmd, cwd=None, stdin=None: subprocess.CompletedProcess(cmd, 1, fake, "")
        try:
            with redirect_stdout(io.StringIO()):
                golden_path.stage_doctor()
        finally:
            golden_path.run = original
        self.assertEqual(golden_path.results, [{"stage": "doctor", "ok": False, "detail": "ready=False failing=['outputs/ writable']"}])

    def test_expected_numbers_are_derived_not_typed(self):
        src = golden_path.__file__
        text = Path(src).read_text(encoding="utf-8")
        # no literal slide/finding/requirement counts in the runner
        self.assertNotRegex(text, r"==\s*(9|14|10|4)\b")

    def test_spec_example_catches_unknown_ids_and_open_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "specs" / "002-x"
            spec.mkdir(parents=True)
            (spec / "spec.md").write_text("# Spec\nTouches SN-REQ-001 and new SN-REQ-042.\n", encoding="utf-8")
            (spec / "plan.md").write_text("# Plan\nadd: SN-REQ-042; also SN-REQ-777 [NEEDS CLARIFICATION]\n", encoding="utf-8")
            (spec / "tasks.md").write_text("no title\n", encoding="utf-8")
            real_root = golden_path.ROOT
            golden_path.ROOT = Path(tmp)
            shutil.copytree(SYSTEM, Path(tmp) / "example-system")
            golden_path.SYSTEM = Path(tmp) / "example-system"
            try:
                with redirect_stdout(io.StringIO()):
                    golden_path.stage_spec_example()
            finally:
                golden_path.ROOT, golden_path.SYSTEM = real_root, SYSTEM
        r = golden_path.results[-1]
        self.assertFalse(r["ok"])
        self.assertIn("002-x/plan.md still has [NEEDS CLARIFICATION]", r["detail"])
        self.assertIn("002-x/plan.md references unknown SN-REQ-777", r["detail"])
        self.assertIn("002-x/tasks.md missing or has no title", r["detail"])
        self.assertNotIn("SN-REQ-042", r["detail"])

    def test_a_crashing_stage_is_a_failed_stage(self):
        original = golden_path.stage_doctor

        def boom():
            raise RuntimeError("kaboom")

        boom.__name__ = "stage_doctor"
        golden_path.stage_doctor = boom
        try:
            with redirect_stdout(io.StringIO()):
                code = golden_path.main(["--skip-tests"])
        finally:
            golden_path.stage_doctor = original
        self.assertEqual(code, 1)
        self.assertEqual([r["detail"] for r in golden_path.results if r["stage"] == "doctor"], ["RuntimeError: kaboom"])


if __name__ == "__main__":
    unittest.main()
