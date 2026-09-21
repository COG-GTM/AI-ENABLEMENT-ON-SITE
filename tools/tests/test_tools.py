"""Tests for the helper scripts in tools/. Run: python -m unittest discover -s tools/tests -q"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_deck  # noqa: E402
import research_brief  # noqa: E402
import tracker_report  # noqa: E402
import what_if  # noqa: E402


class TrackerReportTests(unittest.TestCase):
    def test_example_tracker_validates_and_summarises(self):
        items = tracker_report.load(tracker_report.DEFAULT)
        s = tracker_report.summarise(items)
        self.assertEqual(s["total"], len(items))
        self.assertEqual(s["open"] + s["closed"], s["total"])
        self.assertLessEqual(len(s["top_open"]), 5)
        self.assertEqual(s["top_open"][0]["severity"], "high")

    def test_schema_enums_match_validator(self):
        schema = json.loads(tracker_report.SCHEMA.read_text())
        self.assertEqual(set(tracker_report.SEV_ORDER), set(schema["properties"]["severity"]["enum"]))
        self.assertTrue(set(tracker_report.OPEN_STATES) < set(schema["properties"]["status"]["enum"]))

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


if __name__ == "__main__":
    unittest.main()
