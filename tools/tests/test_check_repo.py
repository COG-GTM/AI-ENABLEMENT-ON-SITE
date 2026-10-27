"""Tests for repository web-fixture gating."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_repo  # noqa: E402


class CheckRepoWebGateTests(unittest.TestCase):
    def test_browser_channel_skips_bundled_probe_and_reports_e2e_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            web = root / "example-system" / "web-app"
            for project in ("react-prototype", "angular-app", "e2e"):
                (web / project / "node_modules").mkdir(parents=True)
            problems: list[str] = []
            output = io.StringIO()

            def fake_run(command, **kwargs):
                failed = command[-1] in ("e2e:react", "e2e:angular")
                return subprocess.CompletedProcess(
                    command, 1 if failed else 0, stdout="", stderr="browser launch failed" if failed else ""
                )

            with (
                mock.patch.object(check_repo, "ROOT", root),
                mock.patch.object(check_repo.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                mock.patch.object(check_repo, "problems", problems),
                mock.patch.object(check_repo.subprocess, "run", side_effect=fake_run) as run,
                mock.patch.dict(os.environ, {"BROWSER_CHANNEL": "chrome"}),
                contextlib.redirect_stdout(output),
            ):
                check_repo.check_web_fixture()

        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any(command[:2] == ["/usr/bin/node", "-e"] for command in commands))
        self.assertIn(["/usr/bin/npm", "run", "e2e:react"], commands)
        self.assertIn(["/usr/bin/npm", "run", "e2e:angular"], commands)
        self.assertIn("BROWSER_CHANNEL=chrome; skipping bundled Chromium probe", output.getvalue())
        self.assertTrue(any("npm run e2e:react exited 1" in problem for problem in problems))
        self.assertTrue(any("npm run e2e:angular exited 1" in problem for problem in problems))

    def test_non_chrome_browser_channel_keeps_bundled_chromium_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            web = root / "example-system" / "web-app"
            for project in ("react-prototype", "angular-app", "e2e"):
                (web / project / "node_modules").mkdir(parents=True)
            problems: list[str] = []
            output = io.StringIO()

            def fake_run(command, **kwargs):
                probe_failed = command[:2] == ["/usr/bin/node", "-e"]
                return subprocess.CompletedProcess(command, 3 if probe_failed else 0, stdout="", stderr="")

            with (
                mock.patch.object(check_repo, "ROOT", root),
                mock.patch.object(check_repo.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                mock.patch.object(check_repo, "problems", problems),
                mock.patch.object(check_repo.subprocess, "run", side_effect=fake_run) as run,
                mock.patch.dict(os.environ, {"BROWSER_CHANNEL": "firefox"}),
                contextlib.redirect_stdout(output),
            ):
                check_repo.check_web_fixture()

        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command[:2] == ["/usr/bin/node", "-e"] for command in commands))
        self.assertFalse(any(command[-1] in ("e2e:react", "e2e:angular") for command in commands))
        self.assertIn("Playwright Chromium browser is not installed; skipped", output.getvalue())
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
