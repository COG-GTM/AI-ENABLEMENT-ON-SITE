import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REACT_FIXTURE = ROOT / "example-system" / "web-app" / "react-prototype" / "public" / "requests.json"
ANGULAR_FIXTURE = ROOT / "example-system" / "web-app" / "angular-app" / "public" / "requests.json"


class WebFixtureTests(unittest.TestCase):
    def test_react_and_angular_request_fixtures_are_identical(self):
        with REACT_FIXTURE.open(encoding="utf-8") as react_file:
            react = json.load(react_file)
        with ANGULAR_FIXTURE.open(encoding="utf-8") as angular_file:
            angular = json.load(angular_file)
        self.assertEqual(react, angular)


if __name__ == "__main__":
    unittest.main()
