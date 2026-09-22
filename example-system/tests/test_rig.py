"""LabVIEW rig reconstruction: bench/rig.py must reproduce bench/rig_recording.csv from bench/rig_samples.csv.
Run: python -m unittest example-system/tests/test_rig.py -q  (from repo root)"""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

SYSTEM = Path(__file__).resolve().parents[1]
ROOT = SYSTEM.parent
sys.path.insert(0, str(SYSTEM / "bench"))
sys.path.insert(0, str(ROOT / "tools"))

import bench_compare  # noqa: E402
import rig  # noqa: E402

BENCH = SYSTEM / "bench"
RECORDING = BENCH / "rig_recording.csv"
SAMPLES = BENCH / "rig_samples.csv"


class RigTests(unittest.TestCase):
    def test_replay_reproduces_recording_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "rig-python.csv"
            rig.write_results(out, rig.replay(SAMPLES))
            r = bench_compare.compare(RECORDING, out, {})
            self.assertEqual(r["verdict"], "PASS", r["problems"])
            self.assertEqual(r["rows_expected"], 3)
            self.assertEqual(sorted(c["column"] for c in r["columns"]), sorted(rig.RESULT_FIELDS))

    def test_recording_has_a_fail_row_and_a_rounding_tie(self):
        with RECORDING.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["verdict"] for r in rows], ["PASS", "PASS", "FAIL"])
        groups = rig.load_samples(SAMPLES)
        ties = {step for (step, _), (temps, _) in groups.items() if (sum(temps) / len(temps)) % 1 == 0.5}
        self.assertEqual(ties, {1, 2}, "RIG-REVIEW.md promises steps 1 and 2 are x.5 ties")

    def test_round_to_nearest_is_half_to_even(self):
        self.assertEqual(rig.round_to_nearest(2500.5), 2500)
        self.assertEqual(rig.round_to_nearest(5023.5), 5024)
        self.assertEqual(rig.round_to_nearest(-0.5), 0)
        self.assertEqual(rig.round_to_nearest(8103.75), 8104)

    def test_compute_step_verdicts(self):
        ok = rig.compute_step(1, 25, [2500] * 4, [8192] * 4)
        self.assertEqual((ok.temp_ok, ok.imu_ok, ok.verdict, ok.max_dev_cc), (True, True, "PASS", 0))
        edge = rig.compute_step(2, 25, [2650] * 4, [8392] * 4)  # exactly at both tolerances
        self.assertEqual(edge.verdict, "PASS")
        bad_imu = rig.compute_step(3, 25, [2500] * 4, [8393] * 4)
        self.assertEqual((bad_imu.temp_ok, bad_imu.imu_ok, bad_imu.verdict), (True, False, "FAIL"))
        self.assertEqual(bad_imu.as_row()[6:], ["TRUE", "FALSE", "FAIL"])

    def test_live_loop_uses_injected_hardware_and_no_real_wait(self):
        calls = {"chamber": [], "settle": 0}
        packets = iter([(2500, 8192)] * 8 + [(5000, 8192)] * 8)
        results = rig.run_soak(read_packet=lambda: next(packets), set_chamber=calls["chamber"].append,
                               settle=lambda: calls.__setitem__("settle", calls["settle"] + 1),
                               setpoints_c=(25, 50))
        self.assertEqual([r.verdict for r in results], ["PASS", "PASS"])
        self.assertEqual(calls["chamber"], [25, 50, 25])  # cleanup frame returns to 25
        self.assertEqual(calls["settle"], 2)

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            rig.compute_step(1, 25, [], [])
        with self.assertRaises(ValueError):
            rig.compute_step(1, 25, [40000], [0])
        with self.assertRaises(ValueError):
            rig.run_soak(lambda: (0, 0), lambda _: None, lambda: None, samples_per_step=0)
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.csv"
            bad.write_text("step,temp_cc\n1,2\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                rig.load_samples(bad)
            bad.write_text("step,setpoint_c,sample_idx,t_ms,temp_cc,acc_z\n1,25,0,0,abc,0\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                rig.load_samples(bad)


if __name__ == "__main__":
    unittest.main()
