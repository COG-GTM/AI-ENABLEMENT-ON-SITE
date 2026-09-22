"""Tests for the helper scripts in tools/. Run: python -m unittest discover -s tools/tests -q"""

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_deck  # noqa: E402
import doctor  # noqa: E402
import research_brief  # noqa: E402
import tracker_report  # noqa: E402
import what_if  # noqa: E402


class DoctorTests(unittest.TestCase):
    def test_repo_is_ready_here(self):
        rows = doctor.run_all()
        self.assertEqual([r["check"] for r in rows if r["status"] == "FAIL"], [])
        self.assertTrue({r["status"] for r in rows} <= {"OK", "SKIP", "FAIL"})
        self.assertIn("READY", doctor.render(rows))

    def test_skill_count_matches_disk(self):
        skills = [r for r in doctor.run_all() if r["check"] == "Skills"][0]
        on_disk = sorted(p.name for p in (ROOT / ".devin" / "skills").iterdir() if (p / "SKILL.md").is_file())
        self.assertIn(f"{len(on_disk)} found", skills["detail"])
        for name in on_disk:
            self.assertIn(name, skills["detail"])

    def test_json_output_and_exit_codes(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = doctor.main(["--json"])
        data = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(data["ready"])
        self.assertEqual(len(data["checks"]), len(doctor.run_all()))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(["--bogus"]), 2)

    def test_broken_mcp_config_is_reported(self):
        real = doctor.ROOT
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td)
            (fake / ".devin").mkdir()
            (fake / ".devin" / "mcp_config.json").write_text('{"mcpServers": {"x": {"command": "python3", "args": ["missing/server.py"]}}}')
            doctor.ROOT = fake
            try:
                r = doctor.check_mcp_config()
            finally:
                doctor.ROOT = real
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("missing/server.py", r["detail"])

    def test_malformed_mcp_shapes_fail_instead_of_raising(self):
        cases = {
            "[]": "non-empty object",
            '{"mcpServers": {"x": 5}}': "must be an object",
            '{"mcpServers": {"x": {"command": ""}}}': "missing command",
            '{"mcpServers": {"x": {"command": "python3", "args": null}}}': "list of strings",
            '{"mcpServers": {"x": {"command": "no-such-binary-for-doctor"}}}': "not found on PATH",
        }
        real = doctor.ROOT
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td)
            (fake / ".devin").mkdir()
            doctor.ROOT = fake
            try:
                for body, expect in cases.items():
                    (fake / ".devin" / "mcp_config.json").write_text(body)
                    r = doctor.check_mcp_config()
                    self.assertEqual(r["status"], "FAIL", body)
                    self.assertIn(expect, r["detail"], body)
            finally:
                doctor.ROOT = real

    def test_outputs_check_does_not_create_directory(self):
        real = doctor.ROOT
        with tempfile.TemporaryDirectory() as td:
            doctor.ROOT = Path(td)
            try:
                r = doctor.check_outputs_writable()
            finally:
                doctor.ROOT = real
            self.assertEqual(r["status"], "OK")
            self.assertFalse((Path(td) / "outputs").exists())


class CheckRepoTests(unittest.TestCase):
    def _with_skills(self, skills: dict[str, str]):
        import check_repo
        td = tempfile.TemporaryDirectory()
        for name, fm in skills.items():
            d = Path(td.name) / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\n{fm}\n---\nbody\n")
        real, check_repo.SKILLS, check_repo.problems = check_repo.SKILLS, Path(td.name), []
        try:
            names = check_repo.check_skills()
            return names, list(check_repo.problems)
        finally:
            check_repo.SKILLS = real
            td.cleanup()

    def test_unknown_frontmatter_key_is_rejected(self):
        _, problems = self._with_skills({"good": "name: good\ndescription: a perfectly fine description here",
                                         "bad": "name: bad\ndescription: a perfectly fine description here\ntools: [exec]"})
        self.assertEqual(len(problems), 1)
        self.assertIn("unknown frontmatter key 'tools'", problems[0])

    def test_skill_cap_enforced(self):
        import check_repo
        many = {f"s{n}": f"name: s{n}\ndescription: a perfectly fine description here" for n in range(check_repo.MAX_SKILLS + 1)}
        _, problems = self._with_skills(many)
        self.assertTrue(any("cap is" in p for p in problems))

    def test_routing_docs_only_mention_real_skills(self):
        import check_repo
        check_repo.problems = []
        check_repo.check_agents(set(check_repo.check_skills()))
        self.assertEqual(check_repo.problems, [])
        check_repo.problems = []
        check_repo.check_agents({"tour"})
        self.assertTrue(any("README.md mentions /exec-deck" in p for p in check_repo.problems))
        check_repo.problems = []

    def test_slash_regex_sees_fenced_and_plain_forms_but_not_paths(self):
        import check_repo
        text = "\n".join([
            "| swap a part | `/what-if-part-swap` |",
            "```text",
            "/exec-deck Design review deck",
            "```",
            "then paste /tdd and wait",
            "see tools/build_deck.py and https://example.invalid/not-a-skill",
            "outputs/x.md and example-system/docs/ICD.md",
        ])
        self.assertEqual(set(check_repo.SLASH_RE.findall(text)), {"what-if-part-swap", "exec-deck", "tdd"})


class TrackerReportTests(unittest.TestCase):
    def test_example_tracker_validates_and_summarises(self):
        items = tracker_report.load(tracker_report.DEFAULT)
        s = tracker_report.summarise(items)
        self.assertEqual(s["total"], len(items))
        self.assertEqual(s["open"] + s["closed"] + s["wont_fix"], s["total"])
        self.assertLessEqual(len(s["top_open"]), 5)
        self.assertEqual(s["top_open"][0]["severity"], "high")

    def test_schema_enums_match_validator(self):
        schema = json.loads(tracker_report.SCHEMA.read_text())
        self.assertEqual(set(tracker_report.SEV_ORDER), set(schema["properties"]["severity"]["enum"]))
        # every status the schema allows lands in exactly one headline bucket
        self.assertEqual(set(tracker_report.OPEN_STATES) | {"closed", "wont_fix"}, set(schema["properties"]["status"]["enum"]))

    def test_every_status_is_counted_once(self):
        items = tracker_report.load(tracker_report.DEFAULT)
        schema = json.loads(tracker_report.SCHEMA.read_text())
        for n, status in enumerate(schema["properties"]["status"]["enum"]):
            items[n]["status"] = status
        s = tracker_report.summarise(items)
        self.assertEqual(s["open"] + s["closed"] + s["wont_fix"], s["total"])
        self.assertEqual(s["wont_fix"], 1)
        self.assertIn("1 won't fix", tracker_report.render_text(s))
        self.assertIn("1 won't fix", tracker_report.render_markdown(s))

    def test_bad_item_rejected(self):
        bad = {"items": [{"id": "SN-BUG-1", "type": "bug", "title": "x", "severity": "huge", "status": "open",
                          "component": "c", "requirements": [], "hazards": [], "opened": "2026-01-01",
                          "closed": None, "owner": "r", "notes": ""}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
        with self.assertRaises(SystemExit) as cm:
            tracker_report.load(Path(f.name))
        self.assertIn("severity", str(cm.exception))
        self.assertIn("id must match", str(cm.exception))


class WhatIfTests(unittest.TestCase):
    def test_baseline_matches_power_budget_doc(self):
        rows = what_if.budget(what_if.load_part("mcu-m0"), what_if.load_part("imu-a"), what_if.load_part("temp-x"), None, 0.40)
        total = sum(r["avg_ma"] for r in rows)
        self.assertAlmostEqual(total, 2.97, places=2)
        self.assertAlmostEqual(2000 / total / 24, 28.1, places=1)

    def test_imu_b_flags_who_am_i_and_burst(self):
        issues = what_if.compatibility(what_if.load_part("imu-b"), what_if.load_part("imu-a"), what_if.load_part("temp-x"))
        joined = " ".join(issues)
        self.assertIn("WHO_AM_I", joined)
        self.assertIn("Burst read", joined)
        self.assertNotIn("Interface changes", joined)

    def test_imu_c_flags_interface_and_scale(self):
        issues = what_if.compatibility(what_if.load_part("imu-c"), what_if.load_part("imu-a"), what_if.load_part("temp-x"))
        joined = " ".join(issues)
        self.assertIn("SPI -> I2C", joined)
        self.assertIn("scale factor", joined)

    def test_unknown_part_rejected(self):
        with self.assertRaises(SystemExit):
            what_if.load_part("../etc/passwd")
        with self.assertRaises(SystemExit):
            what_if.load_part("nope")

    def test_cli_exit_codes(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(what_if.main([]), 2)  # baseline fails the budget
            self.assertEqual(what_if.main(["--imu", "imu-b", "--mcu-duty", "0.25"]), 0)

    def test_mcu_duty_must_be_a_fraction(self):
        parts = (what_if.load_part("mcu-m0"), what_if.load_part("imu-a"), what_if.load_part("temp-x"), None)
        for bad in (-0.1, 1.5, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                what_if.budget(*parts, bad)
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                what_if.main(["--mcu-duty", str(bad)])
        what_if.budget(*parts, 0.0)
        what_if.budget(*parts, 1.0)

    def test_odr_tolerance_matches_srs(self):
        srs = (ROOT / "example-system" / "docs" / "SRS.md").read_text()
        row = next(line for line in srs.splitlines() if line.startswith("| SN-REQ-001 "))
        self.assertIn(f"{what_if.IMU_RATE_HZ} Hz (+/- {what_if.IMU_RATE_TOL * 100:g} %)", row)

    def test_every_part_odr_is_judged_against_srs_tolerance(self):
        base, temp = what_if.load_part("imu-a"), what_if.load_part("temp-x")
        self.assertIn(100, base["odr_hz"])  # the baseline part must itself meet SN-REQ-001
        near_miss = dict(base, odr_hz=[52, 104, 208])  # 4 % off: fine at 5 %, not at 1 %
        self.assertTrue(any("No ODR within 1 %" in i for i in what_if.compatibility(near_miss, base, temp)))
        exact = dict(base, odr_hz=[100.5])
        self.assertFalse(any("ODR" in i for i in what_if.compatibility(exact, base, temp)))


class BuildDeckTests(unittest.TestCase):
    def test_example_outline_builds_self_contained_html(self):
        outline = json.loads((ROOT / "templates" / "deck-outline-example.json").read_text())
        out = build_deck.build(outline)
        self.assertEqual(out.count("<section"), len(outline["slides"]))
        self.assertNotIn("http://", out)
        self.assertNotIn("https://", out)
        self.assertIn("<style>", out)

    def test_example_outline_numbers_match_sources(self):
        """Every number on the example deck must be reproducible from the repository, not typed in."""
        outline = json.loads((ROOT / "templates" / "deck-outline-example.json").read_text())
        stats = {s["label"]: s["value"] for s in outline["slides"][1]["stats"]}
        srs = (ROOT / "example-system" / "docs" / "SRS.md").read_text()
        hazards = [l for l in (ROOT / "example-system" / "docs" / "HAZARDS.md").read_text().splitlines() if l.startswith("| SN-HAZ-")]
        tracker = tracker_report.summarise(tracker_report.load(ROOT / "example-system" / "tracker.json"))
        rows = what_if.budget(what_if.load_part("mcu-m0"), what_if.load_part("imu-a"), what_if.load_part("temp-x"), None, 0.40)
        total = sum(r["avg_ma"] for r in rows)
        by_consumer = {r["consumer"]: r["avg_ma"] for r in rows}

        self.assertEqual(stats["requirements, all with tests or budgets"], str(len([l for l in srs.splitlines() if l.startswith("| SN-REQ-")])))
        self.assertEqual(stats["days battery life (target 30)"], f"{2000 / total / 24:.1f}")
        self.assertEqual(stats["hazards with open mitigation"], f"{sum('Open' in h for h in hazards)} / {len(hazards)}")
        self.assertEqual(stats["open tracker items"], str(tracker["open"]))

        bars = {b["label"]: b["value"] for b in outline["slides"][4]["bars"]}
        self.assertAlmostEqual(bars["MCU active (40 % duty)"], by_consumer["MCU active"], places=2)
        self.assertAlmostEqual(bars["IMU"], by_consumer["IMU (SPI)"], places=2)
        self.assertAlmostEqual(bars["Everything else"], total - by_consumer["MCU active"] - by_consumer["IMU (SPI)"], places=2)
        self.assertIn(f"Total {total:.2f} mA", outline["slides"][4]["note"])

    def test_html_is_escaped(self):
        out = build_deck.build({"title": "<b>x</b>", "slides": [{"type": "bullets", "title": "t", "bullets": ["<script>alert(1)</script>"]}]})
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)

    def test_unknown_slide_type_rejected(self):
        with self.assertRaises(SystemExit):
            build_deck.build({"title": "t", "slides": [{"type": "video"}]})

    def test_too_many_bullets_rejected(self):
        with self.assertRaises(SystemExit):
            build_deck.build({"title": "t", "slides": [{"type": "bullets", "title": "t", "bullets": list("abcdefghi")}]})


class ResearchBriefTests(unittest.TestCase):
    def test_example_is_valid_and_renders(self):
        b = json.loads(research_brief.EXAMPLE.read_text())
        self.assertEqual(research_brief.validate(b), [])
        md = research_brief.to_markdown(b)
        h = research_brief.to_html(b)
        for s in b["sources"]:
            self.assertIn(s["id"], md)
            self.assertIn(s["id"], h)
        self.assertIn("## Bottom line", md)

    def test_uncited_claim_rejected(self):
        b = json.loads(research_brief.EXAMPLE.read_text())
        b["findings"][0]["sources"] = []
        self.assertTrue(any("needs at least one source" in e for e in research_brief.validate(b)))

    def test_unverified_url_rejected(self):
        b = json.loads(research_brief.EXAMPLE.read_text())
        b["sources"][0]["location"] = "https://example.invalid/page"
        self.assertTrue(any("verified" in e for e in research_brief.validate(b)))
        b["sources"][0]["verified"] = True
        self.assertEqual(research_brief.validate(b), [])

    def test_dates_must_be_real_calendar_dates(self):
        for bad in ("2026-13-01", "2026-02-30", "2026-2-3", "20260203", "yesterday", 20260203):
            b = json.loads(research_brief.EXAMPLE.read_text())
            b["date"] = bad
            self.assertTrue(any(e.startswith("date must be") for e in research_brief.validate(b)), bad)
            b = json.loads(research_brief.EXAMPLE.read_text())
            b["sources"][1]["date"] = bad
            self.assertTrue(any("S2: date must be" in e for e in research_brief.validate(b)), bad)
        b = json.loads(research_brief.EXAMPLE.read_text())
        b["date"] = b["sources"][1]["date"] = "2024-02-29"
        self.assertEqual(research_brief.validate(b), [])

    def test_markdown_table_cells_survive_pipes_and_newlines(self):
        b = json.loads(research_brief.EXAMPLE.read_text())
        b["findings"][0]["claim"] = "A | B\nsecond line"
        b["findings"][0]["note"] = "x|y"
        md = research_brief.to_markdown(b)
        table = [line for line in md.splitlines() if line.startswith("| 1 |")]
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0].count("|") - table[0].count("\\|"), 5)  # 4 columns, unescaped pipes only
        self.assertIn("A \\| B second line (x\\|y)", table[0])

    def test_markdown_cell_pipe_stays_escaped_after_a_backslash(self):
        # a pipe is only escaped when preceded by an odd run of backslashes
        for raw in ("A \\| B", "C:\\dir|x", "\\\\|"):
            cell = research_brief.md_cell(raw)
            for m in re.finditer(r"\|", cell):
                run = len(cell[:m.start()]) - len(cell[:m.start()].rstrip("\\"))
                self.assertEqual(run % 2, 1, (raw, cell))


if __name__ == "__main__":
    unittest.main()
