"""m_fleet_scan.py: lexer, resolution, classification, backlog, and --check on the checked-in fixture."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import m_fleet_scan as m  # noqa: E402

PY = sys.executable


def write(tree: Path, rel: str, text: str) -> None:
    p = tree / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Lexer(unittest.TestCase):
    def test_strings_comments_transposes(self):
        code, strings = m.strip_code("x = a' + b(1)'; % comment with call(1)\ns = 'q(2)'; t = \"w(3)\"; u = [1 2]';\n%{\nblock(4)\n%}\ny = f(x, ...\n  2);\n")
        joined = "\n".join(code)
        self.assertNotIn("comment", joined)
        self.assertNotIn("q(2)", joined)
        self.assertNotIn("block", joined)
        self.assertEqual(strings, ["q(2)", "w(3)"])
        self.assertIn("y = f(x,    2)", joined.replace("\n", " ")[:200] + " " + joined)  # continuation joined

    def test_escaped_quote_inside_string(self):
        code, strings = m.strip_code("s = 'it''s'; z = g(1);\n")
        self.assertEqual(strings, ["it's"])
        self.assertIn("g(1)", code[0])


class Resolution(unittest.TestCase):
    def scan(self, files: dict) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree = Path(tmp.name)
        for rel, text in files.items():
            write(tree, rel, text)
        return m.scan_tree(tree)

    def rows(self, result):
        return {r["path"]: r for r in result["rows"]}

    def test_variables_are_not_calls_and_locals_are_not_edges(self):
        r = self.scan({
            "a.m": "function y = a(x)\nv = zeros(3,1);\ny = v(2) + helper(x) + b(x);\nend\nfunction z = helper(q)\nz = q;\nend\n",
            "b.m": "function y = b(x)\ny = x;\nend\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["a.m"]["calls_tree"], "b")
        self.assertEqual(rows["a.m"]["calls_unresolved"], "")
        self.assertEqual(rows["a.m"]["functions"], 2)
        self.assertEqual(rows["b.m"]["callers_count"], 1)
        self.assertEqual([e["kind"] for e in r["dep_map"]["edges"]], ["call"])

    def test_ambiguous_private_package_handle_and_script_kind(self):
        r = self.scan({
            "run_all.m": "helper(1);\ndup(2);\nf = @dup;\npkg.util.tool(3);\n\nfunction local_only()\nend\n",
            "private/helper.m": "function helper(x)\nend\n",
            "one/dup.m": "function dup(x)\nend\n",
            "two/dup.m": "function dup(x)\nend\n",
            "+pkg/+util/tool.m": "function tool(x)\nend\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["run_all.m"]["kind"], "script")  # local function does not make it a function file
        self.assertIn("dup (ambiguous: 2 definitions)", rows["run_all.m"]["calls_unresolved"])
        kinds = sorted(e["kind"] for e in r["dep_map"]["edges"])
        self.assertEqual(kinds, ["ambiguous", "ambiguous", "package", "private"])
        self.assertEqual(rows["+pkg/+util/tool.m"]["kind"], "package function")
        self.assertEqual(rows["private/helper.m"]["kind"], "private function")
        self.assertEqual(r["summary"]["entry_points"], ["run_all.m"])

    def test_dynamic_literal_resolves_and_computed_stays_unresolved(self):
        r = self.scan({
            "d.m": "function d(name)\nf = str2func('target');\nf(1);\nfeval(name, 2);\neval(['tar' 'get']);\nend\n",
            "target.m": "function target(x)\nend\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["d.m"]["calls_tree"], "target (dynamic-literal)")
        self.assertEqual(rows["d.m"]["dynamic_calls"], "eval;feval;str2func")
        self.assertIn("dynamic call (eval, feval, str2func; 1 of 3 with a string literal)", rows["d.m"]["reasons"])
        self.assertEqual(r["dep_map"]["dynamic"]["d.m"], ["eval (computed)", "feval (computed)", "str2func (string literal)"])

    def test_unrelated_strings_do_not_become_dynamic_edges(self):
        r = self.scan({
            "d.m": "function d(name)\ndisp('target');\nfprintf('%s', 'other');\nfeval(name, 2);\nend\n",
            "e.m": "function e()\ndisp('helper text');\nfeval('target', 1);\neval('other(3);');\nend\n",
            "f.m": "function f()\neval('target = 3');\neval('x = other(2)');\neval('target(1) + other(2)');\neval('target(1))');\nend\n",
            "g.m": "function g()\neval('target(other(1), 2);');\nfeval('pkg.target');\nend\n",
            "target.m": "function target(x)\nend\n",
            "other.m": "function other(x)\nend\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["d.m"]["calls_tree"], "")            # 'target' is only displayed, never dispatched
        self.assertEqual(rows["e.m"]["calls_tree"], "other (dynamic-literal);target (dynamic-literal)")
        kinds = {(e["from"], e["to"]): e["kind"] for e in r["dep_map"]["edges"]}
        self.assertNotIn(("d.m", "target.m"), kinds)
        self.assertEqual(rows["f.m"]["calls_tree"], "")            # assignments and expressions are not function names
        self.assertNotIn(("f.m", "target.m"), kinds)
        self.assertNotIn(("f.m", "other.m"), kinds)
        self.assertEqual(kinds[("g.m", "target.m")], "dynamic-literal")   # one balanced call with nested arguments
        self.assertEqual(rows["g.m"]["calls_tree"], "target (dynamic-literal)")
        self.assertEqual(rows["g.m"]["dynamic_calls"], "eval;feval")
        self.assertEqual(kinds[("e.m", "target.m")], "dynamic-literal")
        self.assertEqual(kinds[("e.m", "other.m")], "dynamic-literal")

    def test_classification_retain_wrap_port_shadow(self):
        r = self.scan({
            "s.m": "function s(mdl)\nsim(mdl);\nend\n",
            "w.m": "function y = w(x)\ny = fir1(4, 0.5) + filter(1, 1, x);\nend\n",
            "g.m": "figure; plot(1:3); xlabel('t');\n",
            "max.m": "function m = max(a, b)\nm = builtin('max', a, b);\nend\n",
            "p.m": "function y = p(x)\ny = max(x, 1) + mystery(x);\nend\n",
            "classy.m": "classdef classy\n  methods\n    function obj = classy()\n    end\n    out = declared(obj, x)\n  end\nend\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["s.m"]["classification"], "retain")
        self.assertIn("Simulink API", rows["s.m"]["reasons"])
        self.assertEqual(rows["w.m"]["classification"], "wrap")
        self.assertIn("Signal Processing Toolbox", rows["w.m"]["reasons"])
        self.assertEqual(rows["g.m"]["classification"], "retain")
        self.assertIn("graphics-only", rows["g.m"]["reasons"])
        self.assertEqual(rows["p.m"]["classification"], "port")
        self.assertEqual(rows["p.m"]["calls_unresolved"], "mystery")
        self.assertIn("shadows a built-in: max", rows["p.m"]["reasons"])
        self.assertIn("shadows a MATLAB built-in", rows["max.m"]["reasons"])
        self.assertEqual(r["dep_map"]["shadowing"], [{"path": "max.m", "shadows": "max"}])
        self.assertEqual(rows["classy.m"]["calls_unresolved"], "")  # declared method is local, not a call

    def test_cycles_and_leaf_first_order(self):
        r = self.scan({
            "a.m": "function a()\nb();\nend\n", "b.m": "function b()\na(); c();\nend\n", "c.m": "function c()\nend\n",
        })
        self.assertEqual(r["dep_map"]["leaf_first_order"][0], "c.m")
        self.assertEqual(r["dep_map"]["cycles"], [["a.m", "b.m"]])
        self.assertEqual(r["summary"]["counts"]["cycles"], 1)

    def test_unreadable_and_non_utf8_are_reported_not_fatal(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree = Path(tmp.name)
        (tree / "bad.m").write_bytes(b"\xff\xfefunction y = bad(x)\r\ny = x;\r\nend\r\n")
        (tree / "empty.m").write_text("% only a comment\n", encoding="utf-8")
        rows = self.rows(m.scan_tree(tree))
        self.assertEqual(rows["bad.m"]["kind"], "function")
        self.assertIn("non-UTF-8 bytes replaced", rows["bad.m"]["notes"])
        self.assertEqual(rows["empty.m"]["classification"], "unreadable")

    def test_outputs_backlog_and_rescan_keep_ids(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree, out = Path(tmp.name) / "t", Path(tmp.name) / "out"
        write(tree, "a.m", "function a()\nb();\nend\n")
        write(tree, "b.m", "function b()\nend\n")
        write(tree, "tests/test_a.m", "a();\n")
        paths = m.write_outputs(m.scan_tree(tree), out, "t", 50, "MAT", "2026-01-05")
        for k in ("inventory", "summary", "dependency_map", "dependency_dot", "repo_map", "backlog", "backlog_csv"):
            self.assertTrue(paths[k].is_file(), k)
        items = json.loads(paths["backlog"].read_text())["items"]
        self.assertEqual([i["title"] for i in items], ["Port a (function)", "Port b (function)"])  # tests excluded; a has a test caller (+10)
        items[0]["status"] = "open"
        paths["backlog"].write_text(json.dumps({"items": items}))
        write(tree, "c.m", "function c()\nend\n")
        again = json.loads(m.write_outputs(m.scan_tree(tree), out, "t", 50, "MAT", "2026-02-01")["backlog"].read_text())["items"]
        by_title = {i["title"]: i for i in again}
        self.assertEqual(by_title["Port a (function)"]["status"], "open")
        self.assertEqual(by_title["Port c (function)"]["id"], "MAT-CAP-003")
        self.assertIn("digraph", paths["dependency_dot"].read_text())
        self.assertIn("## Leaf-first migration order", paths["repo_map"].read_text())


class Check(unittest.TestCase):
    def test_check_passes_on_fixture(self):
        r = subprocess.run([PY, "tools/m_fleet_scan.py", "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("m-fleet check ok", r.stdout)

    def test_fixture_exercises_every_finding_kind(self):
        r = m.scan_tree(m.FIXTURE)
        s, d = r["summary"], r["dep_map"]
        self.assertEqual(s["classification"]["unreadable"], 0)
        self.assertGreater(s["counts"]["dynamic_calls"], 0)
        self.assertGreater(s["counts"]["unresolved_names"], 0)
        self.assertTrue(d["shadowing"])
        self.assertTrue(d["orphans"])
        self.assertTrue(d["entry_points"])
        self.assertEqual(sorted({e["kind"] for e in d["edges"]}), ["call", "dynamic-literal", "method-name", "package"])
        kinds = {row["kind"] for row in r["rows"]}
        self.assertTrue({"script", "function", "classdef", "method", "package function", "private function"} <= kinds)


if __name__ == "__main__":
    unittest.main()
