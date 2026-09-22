"""Model-to-code equivalence: model/filter_vectors.csv (from moving_avg.m) vs the firmware twins.
Run: python -m unittest example-system/tests/test_model_equivalence.py -q  (from repo root)
The C leg runs only when a compiler is on PATH; the Python leg always runs."""

import csv
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SYSTEM = Path(__file__).resolve().parents[1]
ROOT = SYSTEM.parent
sys.path.insert(0, str(SYSTEM / "model"))
sys.path.insert(0, str(ROOT / "tools"))

import bench_compare  # noqa: E402
import run_vectors  # noqa: E402

VECTORS = SYSTEM / "model" / "filter_vectors.csv"
WINDOW = 4


def model_rows() -> list[dict[str, int]]:
    with VECTORS.open(newline="", encoding="utf-8") as fh:
        return [{k: int(v) for k, v in row.items()} for row in csv.DictReader(fh)]


def matlab_fix_reference(samples: list[int], n: int = WINDOW) -> list[int]:
    """Literal transcription of moving_avg.m: 1-based window, fix() toward zero."""
    out = []
    for k in range(1, len(samples) + 1):
        lo = max(1, k - n + 1)
        w = samples[lo - 1:k]
        out.append(int(math.trunc(sum(w) / len(w))))
    return out


class ModelEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = model_rows()
        self.samples = [r["sample"] for r in self.rows]
        self.expected = [r["filtered"] for r in self.rows]

    def test_vectors_are_consistent_with_the_m_file(self):
        self.assertEqual([r["k"] for r in self.rows], list(range(1, len(self.rows) + 1)))
        self.assertEqual(matlab_fix_reference(self.samples), self.expected)

    def test_vectors_cover_the_cases_the_notes_promise(self):
        # MODEL-NOTES.md says row k=10 is where fix() and round-to-nearest disagree; keep it so.
        diverge = []
        for k in range(1, len(self.samples) + 1):
            w = self.samples[max(0, k - WINDOW):k]
            mean = sum(w) / len(w)
            nearest = math.floor(mean + 0.5) if mean >= 0 else -math.floor(-mean + 0.5)
            if nearest != self.expected[k - 1]:
                diverge.append(k)
        self.assertIn(10, diverge)
        self.assertEqual(self.samples[9], 0)
        self.assertEqual(sum(self.samples[6:10]), -3)
        self.assertIn(32767, self.samples)
        self.assertIn(-32768, self.samples)

    def test_python_twin_matches_model(self):
        self.assertEqual(run_vectors.run_python(self.samples, WINDOW), self.expected)

    def test_bench_compare_passes_on_python_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "py.csv"
            run_vectors.write_csv(out, self.samples, run_vectors.run_python(self.samples, WINDOW))
            r = bench_compare.compare(VECTORS, out, {})
            self.assertEqual(r["verdict"], "PASS", r["problems"])
            self.assertEqual(sorted(c["column"] for c in r["columns"]), ["filtered", "k", "sample"])

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc") or shutil.which("clang"), "no C compiler")
    def test_c_firmware_matches_model(self):
        self.assertEqual(run_vectors.run_c(self.samples), self.expected)

    def test_run_vectors_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.csv"
            with self.assertRaisesRegex(SystemExit, "not a file"):
                run_vectors.load_samples(bad)
            bad.write_text("k,sample,filtered\n1,40000,0\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                run_vectors.load_samples(bad)
            bad.write_text("k,value\n1,2\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                run_vectors.load_samples(bad)


if __name__ == "__main__":
    unittest.main()
