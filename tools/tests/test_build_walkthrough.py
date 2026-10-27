import unittest
from unittest.mock import patch

from tools import build_walkthrough


EXPECTED_PROMPT_SKILLS = {
    "Ask and plan": ("/react-to-angular", "/spec-driven"),
    "Track": ("/plan-to-tracker",),
    "Migrate leaf-first": ("/tdd",),
    "Iterate the UI": ("/ui-iterate",),
    "Review": ("/sonar-gate",),
}


class WalkthroughBuilderTests(unittest.TestCase):
    def test_each_readme_stage_prompt_starts_with_its_expected_skill(self):
        rows = build_walkthrough.walkthrough_rows()
        self.assertEqual({row[0] for row in rows}, set(EXPECTED_PROMPT_SKILLS))
        for stage, _, _, row_prompt, _ in rows:
            prompts, _ = build_walkthrough.STAGE_GUIDANCE[stage]
            expected_skills = EXPECTED_PROMPT_SKILLS[stage]
            self.assertEqual(len(prompts), len(expected_skills))
            self.assertEqual(row_prompt, " then ".join(prompts))
            self.assertTrue(row_prompt.startswith(expected_skills[0]), row_prompt)
            for prompt, skill in zip(prompts, expected_skills):
                with self.subTest(stage=stage, skill=skill):
                    self.assertTrue(prompt.startswith(skill), prompt)

    def test_readme_stage_without_a_mapping_raises_value_error(self):
        with patch.object(build_walkthrough, "markdown_steps", return_value=[["Unmapped stage", "", ""]]):
            with self.assertRaisesRegex(ValueError, "Unmapped stage"):
                build_walkthrough.walkthrough_rows()


if __name__ == "__main__":
    unittest.main()
