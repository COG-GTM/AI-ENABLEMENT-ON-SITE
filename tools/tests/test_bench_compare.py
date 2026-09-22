"""Tests for tools/bench_compare.py. Run: python -m unittest tools/tests/test_bench_compare.py -q"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import bench_compare  # noqa: E402


class BenchCompareTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def csv(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def run_cli(self, *args) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bench_compare.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_identical_files_pass(self):
        e = self.csv("e.csv", "setpoint_c,mean_temp_cc,pass\n25,2500,TRUE\n50,5001,TRUE\n")
        a = self.csv("a.csv", "setpoint_c,mean_temp_cc,pass\n25,2500,TRUE\n50,5001,TRUE\n")
        code, out, _ = self.run_cli(e, a)
        self.assertEqual(code, 0)
        self.assertIn("-> PASS", out)

    def test_tolerance_boundary_inclusive(self):
        e = self.csv("e.csv", "x\n10.0\n")
        a = self.csv("a.csv", "x\n10.05\n")
        self.assertEqual(self.run_cli(e, a, "--tol", "x=0.05")[0], 0)
        self.assertEqual(self.run_cli(e, a, "--tol", "x=0.04")[0], 2)
        self.assertEqual(self.run_cli(e, a)[0], 2)  # exact by default

    def test_default_tolerance_and_first_divergence(self):
        e = self.csv("e.csv", "x,y\n1,1\n2,2\n3,3\n")
        a = self.csv("a.csv", "x,y\n1,1\n2,2.5\n3,9\n")
        r = bench_compare.compare(e, a, {"*": 0.6})
        y = next(c for c in r["columns"] if c["column"] == "y")
        self.assertEqual(y["mismatches"], 1)
        self.assertEqual(y["first_divergence"], {"row": 4, "expected": "3", "actual": "9"})
        self.assertEqual(y["max_abs_error"], 6.0)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(next(c for c in r["columns"] if c["column"] == "x")["pass"])

    def test_column_order_does_not_matter(self):
        e = self.csv("e.csv", "a,b\n1,2\n")
        a = self.csv("a.csv", "b,a\n2,1\n")
        self.assertEqual(bench_compare.compare(e, a, {})["verdict"], "PASS")

    def test_missing_and_extra_columns_fail(self):
        e = self.csv("e.csv", "a,b\n1,2\n")
        a = self.csv("a.csv", "a,c\n1,2\n")
        r = bench_compare.compare(e, a, {})
        self.assertEqual(r["missing_columns"], ["b"])
        self.assertEqual(r["extra_columns"], ["c"])
        self.assertEqual(r["verdict"], "FAIL")

    def test_row_count_mismatch_fails_but_reports_shared_rows(self):
        e = self.csv("e.csv", "a\n1\n2\n3\n")
        a = self.csv("a.csv", "a\n1\n2\n")
        r = bench_compare.compare(e, a, {})
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("row count differs", r["problems"][0])
        self.assertEqual(r["columns"][0]["rows"], 2)

    def test_text_columns_compare_exactly_and_nan_never_passes(self):
        e = self.csv("e.csv", "state,v\nOK,1\nOK,nan\n")
        a = self.csv("a.csv", "state,v\nok,1\nOK,nan\n")
        r = bench_compare.compare(e, a, {"v": 1e9})
        state = next(c for c in r["columns"] if c["column"] == "state")
        v = next(c for c in r["columns"] if c["column"] == "v")
        self.assertEqual(state["kind"], "text")
        self.assertFalse(state["pass"])
        self.assertFalse(v["pass"])

    def test_bad_inputs_exit_1(self):
        good = self.csv("g.csv", "a\n1\n")
        empty = self.csv("empty.csv", "")
        ragged = self.csv("ragged.csv", "a,b\n1\n")
        dupe = self.csv("dupe.csv", "a,a\n1,2\n")
        weird = self.csv("weird.csv", "a;<script>\n1\n")
        for bad in (empty, ragged, dupe, weird, self.dir / "missing.csv"):
            code, _, err = self.run_cli(good, bad)
            self.assertEqual(code, 1, bad.name)
            self.assertTrue(err.startswith("error:"), bad.name)
        for spec in ("x", "x=", "x=abc", "x=-1", "x=nan", "x=inf", "$(rm)=1"):
            code, _, err = self.run_cli(good, good, "--tol", spec)
            self.assertEqual(code, 1, spec)
        code, _, err = self.run_cli(good, good, "--tol", "zzz=1")
        self.assertEqual(code, 2)  # unknown column named in --tol is a FAIL, not a crash

    def test_markdown_and_json_outputs(self):
        e = self.csv("e.csv", "x\n1\n")
        a = self.csv("a.csv", "x\n2\n")
        code, md, _ = self.run_cli(e, a, "--markdown", "--tol", "x=5")
        self.assertEqual(code, 0)
        self.assertIn("| `x` | numeric | 5 | 1 | 0 / 1 | PASS |", md)
        self.assertTrue(md.rstrip().endswith("-> **PASS**"))
        code, js, _ = self.run_cli(e, a, "--json")
        data = json.loads(js)
        self.assertEqual(code, 2)
        self.assertEqual(data["verdict"], "FAIL")
        self.assertEqual(data["columns"][0]["first_divergence"]["row"], 2)

    def test_blank_lines_and_bom_are_tolerated(self):
        e = self.csv("e.csv", "\ufeffx,y\n1,2\n\n")
        a = self.csv("a.csv", "x,y\n1,2\n")
        self.assertEqual(bench_compare.compare(e, a, {})["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
