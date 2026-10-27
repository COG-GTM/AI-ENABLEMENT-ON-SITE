import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "example-system" / "web-app" / "evidence"
REACT_README = ROOT / "use-cases" / "react-to-angular" / "README.md"
UI_README = ROOT / "use-cases" / "ui-ux-iteration" / "README.md"
REACT_DECK = ROOT / "use-cases" / "react-to-angular" / "deck.json"
UI_DECK = ROOT / "use-cases" / "ui-ux-iteration" / "deck.json"


def e2e_count(run):
    return f"{run['tests_passed']}/{run['tests_passed'] + run['tests_failed']}"


def deck_stats(deck):
    return {
        stat["label"]: stat["value"]
        for slide in deck["slides"]
        if slide.get("type") == "stats"
        for stat in slide["stats"]
    }


class WebEvidenceTests(unittest.TestCase):
    def test_use_case_numbers_match_the_parity_and_ux_evidence(self):
        parity = json.loads((EVIDENCE / "parity.json").read_text(encoding="utf-8"))
        ux = json.loads((EVIDENCE / "ux-upgrade.json").read_text(encoding="utf-8"))
        react_readme = " ".join(REACT_README.read_text(encoding="utf-8").split())
        ui_readme = " ".join(UI_README.read_text(encoding="utf-8").split())
        react_deck = deck_stats(json.loads(REACT_DECK.read_text(encoding="utf-8")))
        ui_deck = deck_stats(json.loads(UI_DECK.read_text(encoding="utf-8")))

        react_baseline = parity["unit"]["react"]
        angular_baseline = parity["unit"]["angular"]
        angular_final = ux["unit"]
        before = parity["shared_e2e_before_ux_upgrade"]
        after = ux["shared_e2e_after_ux_upgrade"]
        self.assertEqual(e2e_count(before["react"]), e2e_count(before["angular"]))
        self.assertEqual(e2e_count(after["react"]), e2e_count(after["angular"]))
        self.assertEqual(react_baseline["tests_failed"], 0)
        self.assertEqual(angular_baseline["tests_failed"], 0)
        self.assertEqual(angular_final["tests_failed"], 0)
        self.assertEqual(after["react"]["axe_violations"], 0)
        self.assertEqual(after["angular"]["axe_violations"], 0)

        self.assertIn(f"**{react_baseline['tests_passed']} React unit tests**", react_readme)
        self.assertIn(f"**{react_baseline['line_coverage_percent']:.2f}%**", react_readme)
        self.assertIn(f"**{angular_baseline['tests_passed']} Angular unit tests**", react_readme)
        self.assertIn(f"**{angular_baseline['line_coverage_percent']:.2f}%**", react_readme)
        self.assertIn(f"**{angular_final['tests_passed']} unit tests**", react_readme)
        self.assertIn(f"**{angular_final['line_coverage_percent']:.2f}%**", react_readme)
        self.assertIn(f"**{e2e_count(before['react'])} tests against each app**", react_readme)
        self.assertIn(f"**{e2e_count(after['react'])} against each app**", react_readme)
        self.assertIn("both post-iteration axe runs recorded zero violations", react_readme)

        self.assertIn(f"**{angular_final['tests_passed']}/{angular_final['tests_passed']} Angular unit tests**", ui_readme)
        self.assertIn(f"**{angular_final['line_coverage_percent']:.2f}%**", ui_readme)
        self.assertIn(f"**{e2e_count(after['react'])} shared Playwright tests on each app**", ui_readme)
        self.assertIn("Both axe runs recorded zero violations.", ui_readme)

        self.assertEqual(
            react_deck["React / Angular baseline / final unit tests"],
            f"{react_baseline['tests_passed']} / {angular_baseline['tests_passed']} / {angular_final['tests_passed']}",
        )
        self.assertEqual(
            react_deck["React line coverage at parity baseline"],
            f"{react_baseline['line_coverage_percent']:.2f}%",
        )
        self.assertEqual(
            react_deck["Angular line coverage before and after UX fixes"],
            f"{angular_baseline['line_coverage_percent']:.2f}% → {angular_final['line_coverage_percent']:.2f}%",
        )
        before_count = e2e_count(before["react"]).replace("/", " / ")
        after_count = e2e_count(after["react"]).replace("/", " / ")
        self.assertEqual(
            react_deck["shared Playwright tests per app, before and after"],
            f"{before_count} → {after_count}",
        )
        self.assertEqual(react_deck["axe violations in both post-UX runs"], "0")

        self.assertEqual(ui_deck["Angular line coverage"], f"{angular_final['line_coverage_percent']:.2f}%")
        self.assertEqual(
            ui_deck["Angular unit tests"],
            f"{angular_final['tests_passed']} / {angular_final['tests_passed']}",
        )
        self.assertEqual(ui_deck["shared e2e tests on each app"], after_count)
        self.assertEqual(ui_deck["axe violations"], "0")


if __name__ == "__main__":
    unittest.main()
