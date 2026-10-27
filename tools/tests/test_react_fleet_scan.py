"""Tests for the deterministic React inventory scanner."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import react_fleet_scan  # noqa: E402
import prompt_pack  # noqa: E402


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
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "scan"
            paths = react_fleet_scan.artifacts(result, output, "fixture", fresh=True)
            items = json.loads(paths["backlog"].read_text(encoding="utf-8"))["items"]
            self.assertTrue(any("RequestForm.tsx (RequestForm)" in item["title"] for item in items))
            self.assertTrue(any("Wrap RequestForm.tsx (RequestForm) to Angular" == item["title"] for item in items))
            packs_dir = Path(temp) / "packs"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(prompt_pack.main(["--map", str(paths["dependency_map"]), "--out-dir", str(packs_dir), "--json"]), 0)
            packs = json.loads((packs_dir / "manifest.json").read_text(encoding="utf-8"))["packs"]
            self.assertEqual({item["id"] for item in items}, {pack["id"] for pack in packs})
            self.assertIn("wrap", {pack["classification"] for pack in packs})

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

    def test_file_backlog_groups_declarations_and_preserves_state_on_rescan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree = root / "src"
            tree.mkdir()
            (tree / "SettingsContext.tsx").write_text(
                "export const SettingsContext = createContext({ units: 'metric' });\n"
                "export function SettingsProvider({ children }) { return <SettingsContext.Provider>{children}</SettingsContext.Provider>; }\n"
                "export function useSettings() { return useContext(SettingsContext); }\n",
                encoding="utf-8",
            )
            (tree / "Zebra.tsx").write_text("export function Zebra() { return <section />; }\n", encoding="utf-8")
            output = root / "scan"
            first = react_fleet_scan.artifacts(
                react_fleet_scan.scan_tree(root), output, "fixture", prefix="REA", opened="2026-01-02", fresh=True
            )
            first_items = json.loads(first["backlog"].read_text(encoding="utf-8"))["items"]
            settings_item = next(item for item in first_items if item["notes"].endswith("path: src/SettingsContext.tsx"))
            self.assertEqual(
                settings_item["title"],
                "Port SettingsContext.tsx (SettingsContext, SettingsProvider, useSettings) to Angular",
            )
            old_id = settings_item["id"]
            settings_item.update(status="in_review", owner="fixture-owner", opened="2025-01-01")
            first["backlog"].write_text(json.dumps({"items": first_items}), encoding="utf-8")
            (tree / "Aardvark.tsx").write_text("export function Aardvark() { return <aside />; }\n", encoding="utf-8")
            second = react_fleet_scan.artifacts(
                react_fleet_scan.scan_tree(root), output, "fixture", prefix="REA", opened="2026-10-27"
            )
            items = json.loads(second["backlog"].read_text(encoding="utf-8"))["items"]
            by_path = {item["notes"].rsplit("path: ", 1)[1]: item for item in items}
            preserved = by_path["src/SettingsContext.tsx"]
            self.assertEqual(preserved["id"], old_id)
            self.assertEqual(preserved["status"], "in_review")
            self.assertEqual(preserved["owner"], "fixture-owner")
            self.assertEqual(preserved["opened"], "2025-01-01")
            self.assertEqual(len(items), len(by_path))
            self.assertEqual(len({item["id"] for item in items}), len(items))
            self.assertNotIn(by_path["src/Aardvark.tsx"]["id"], {item["id"] for item in first_items})


if __name__ == "__main__":
    unittest.main()
