"""Tests for the deterministic React inventory scanner."""

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import react_fleet_scan  # noqa: E402


class ReactFleetScanTests(unittest.TestCase):
    def test_check_matches_committed_expected_fixture(self):
        self.assertEqual(react_fleet_scan.check(), 0)

    def test_units_hooks_imports_routes_and_tests_are_found(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            (tree / "src").mkdir()
            (tree / "src" / "StatusBadge.tsx").write_text(
                "export function StatusBadge({ label }) { return <span>{label}</span>; }\n", encoding="utf-8"
            )
            (tree / "src" / "useRequests.ts").write_text(
                "export function useRequests() { const [items, setItems] = useState([]); return items; }\n", encoding="utf-8"
            )
            (tree / "src" / "RequestForm.tsx").write_text(
                'import { StatusBadge } from "./StatusBadge";\nimport { Button } from "@mui/material";\n'
                "export const RequestForm = () => { const [value, setValue] = useState(''); "
                "useEffect(() => {}, []); const shown = useMemo(() => value, [value]); "
                "useRequests(); return <section><StatusBadge label={shown} /></section>; };\n",
                encoding="utf-8",
            )
            (tree / "src" / "SettingsContext.tsx").write_text(
                "export const SettingsContext = createContext({ units: 'metric' });\n", encoding="utf-8"
            )
            (tree / "src" / "App.tsx").write_text(
                'export const App = () => <Routes><Route path="/requests/:id" /></Routes>;\n', encoding="utf-8"
            )
            (tree / "src" / "RequestForm.test.tsx").write_text(
                "it('renders', () => render(<RequestForm />));\n", encoding="utf-8"
            )
            (tree / "vite.config.ts").write_text("export default {};\n", encoding="utf-8")
            (tree / "package.json").write_text(
                '{"dependencies":{"react":"19.0.0","@mui/material":"7.0.0"}}\n', encoding="utf-8"
            )
            result = react_fleet_scan.scan_tree(tree)

        units = {node["path"]: node for node in result["nodes"]}
        components = {name: node for node in result["nodes"] for name in node["components"]}
        form = components["RequestForm"]
        hook = next(node for node in result["nodes"] if "useRequests" in node["hooks_defined"])
        settings = units["src/SettingsContext.tsx"]
        self.assertIn("StatusBadge", components)
        self.assertTrue(settings["create_context"])
        self.assertEqual(hook["source_classification"], "service")
        self.assertEqual(hook["classification"], "port")
        self.assertIn("Angular target: injectable service or function", " ".join(hook["reasons"]))
        self.assertEqual(units["vite.config.ts"]["classification"], "retain")
        self.assertIn("src/StatusBadge.tsx", form["relative_imports"])
        self.assertEqual(form["classification"], "wrap")
        self.assertIn("custom element or replace UI dependency", form["angular_target"])
        self.assertIn("useState", form["hook_calls"])
        self.assertIn("src/RequestForm.test.tsx", form["test_references"])
        self.assertIn("/requests/:id", units["src/App.tsx"]["routes"])
        self.assertIn("useMemo", {row["react"] for row in result["concept_mappings"]})
        self.assertLess(result["leaf_first_order"].index("src/StatusBadge.tsx"),
                        result["leaf_first_order"].index("src/RequestForm.tsx"))

    def test_scanner_skips_dependency_and_build_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            for folder in ("src", "node_modules/pkg", "dist"):
                (tree / folder).mkdir(parents=True, exist_ok=True)
            (tree / "src" / "main.tsx").write_text("export const Root = () => <main />;\n", encoding="utf-8")
            (tree / "node_modules" / "pkg" / "ignored.ts").write_text("export const Ignored = () => <div />;\n", encoding="utf-8")
            (tree / "dist" / "ignored.js").write_text("export const Ignored = () => <div />;\n", encoding="utf-8")
            result = react_fleet_scan.scan_tree(tree)
        self.assertEqual(result["counts"]["files"], 1)
        self.assertEqual([node["path"] for node in result["nodes"] if node["kind"] == "component"], ["src/main.tsx"])


if __name__ == "__main__":
    unittest.main()
