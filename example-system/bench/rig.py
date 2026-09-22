#!/usr/bin/env python3
"""Python reconstruction of `Thermal Soak Test.vi` (see rig.vi.html), the output of /labview-to-python.

Two ways to run it:

    # Offline replay: feed the raw samples the LabVIEW rig logged, regenerate the results table,
    # then let bench_compare.py say whether this port agrees with what LabVIEW recorded.
    python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv
    python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv

    # Live: pass your own `read_packet` / `set_chamber` callables to run_soak() (pyserial, pyvisa,
    # or the vendor's Python driver). Nothing in this file opens hardware on its own.

What is reproduced: per-step statistics, rounding, verdicts, CSV row format.
What is NOT reproduced and must be reviewed on the bench: settle timing (Wait (ms)), VISA/serial
error behaviour, the chamber's own controller, and the error-cluster skip-a-step path. See RIG-REVIEW.md.
"""

import argparse
import csv
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_SAMPLE_ROWS = 100_000
INT16 = range(-32768, 32768)

# Connector-pane defaults from rig.vi.html.
DEFAULT_SETPOINTS_C = (25, 50, 75)
DEFAULT_SAMPLES_PER_STEP = 8
TEMP_TOL_CC = 150
ACC_Z_NOMINAL = 8192
ACC_Z_TOL = 200

# The type the VI returns: one cluster per step, in this field order.
RESULT_FIELDS = ("step", "setpoint_c", "samples", "mean_temp_cc", "max_dev_cc", "acc_z_mean", "temp_ok", "imu_ok", "verdict")

ReadPacket = Callable[[], tuple[int, int]]  # -> (temp_cc, acc_z), like Read Node Packet.vi
SetChamber = Callable[[int], None]          # like Chamber Set Temp.vi


def round_to_nearest(x: float) -> int:
    """LabVIEW's Round To Nearest: ties go to the even integer. Python's round() does the same;
    C's (int)(x + 0.5) does not, which is why this is its own named function."""
    return int(round(x))


@dataclass(frozen=True)
class StepResult:
    step: int
    setpoint_c: int
    samples: int
    mean_temp_cc: int
    max_dev_cc: int
    acc_z_mean: int
    temp_ok: bool
    imu_ok: bool

    @property
    def verdict(self) -> str:
        return "PASS" if self.temp_ok and self.imu_ok else "FAIL"

    def as_row(self) -> list[str]:
        tf = {True: "TRUE", False: "FALSE"}  # Log Row.vi spells Booleans this way
        return [str(self.step), str(self.setpoint_c), str(self.samples), str(self.mean_temp_cc), str(self.max_dev_cc),
                str(self.acc_z_mean), tf[self.temp_ok], tf[self.imu_ok], self.verdict]


def compute_step(step: int, setpoint_c: int, temps: list[int], accs: list[int],
                 temp_tol_cc: int = TEMP_TOL_CC, acc_z_nominal: int = ACC_Z_NOMINAL, acc_z_tol: int = ACC_Z_TOL) -> StepResult:
    """Compute Stats.vi plus the two comparisons that follow it on the diagram."""
    if not temps or len(temps) != len(accs):
        raise ValueError(f"step {step}: need equal, non-empty temp and acc sample lists")
    for v in (*temps, *accs):
        if v not in INT16:
            raise ValueError(f"step {step}: sample {v} outside int16")
    mean_temp_cc = round_to_nearest(sum(temps) / len(temps))
    max_dev_cc = max(abs(t - mean_temp_cc) for t in temps)
    acc_z_mean = round_to_nearest(sum(accs) / len(accs))
    return StepResult(
        step=step, setpoint_c=setpoint_c, samples=len(temps),
        mean_temp_cc=mean_temp_cc, max_dev_cc=max_dev_cc, acc_z_mean=acc_z_mean,
        temp_ok=abs(mean_temp_cc - setpoint_c * 100) <= temp_tol_cc,
        imu_ok=abs(acc_z_mean - acc_z_nominal) <= acc_z_tol,
    )


def run_soak(read_packet: ReadPacket, set_chamber: SetChamber, settle: Callable[[], None],
             setpoints_c: Iterable[int] = DEFAULT_SETPOINTS_C, samples_per_step: int = DEFAULT_SAMPLES_PER_STEP) -> list[StepResult]:
    """The outer For Loop of the VI, with hardware and waiting injected so tests can run without either."""
    if not 1 <= samples_per_step <= 10_000:
        raise ValueError("samples_per_step must be 1..10000")
    results = []
    try:
        for step, sp in enumerate(setpoints_c, start=1):
            set_chamber(sp)
            settle()
            pairs = [read_packet() for _ in range(samples_per_step)]
            results.append(compute_step(step, sp, [t for t, _ in pairs], [a for _, a in pairs]))
    finally:
        set_chamber(DEFAULT_SETPOINTS_C[0])  # cleanup frame runs on the error path too, as the VI's does
    return results


def load_samples(path: Path) -> dict[tuple[int, int], tuple[list[int], list[int]]]:
    """Read rig_samples.csv (step, setpoint_c, sample_idx, t_ms, temp_cc, acc_z) grouped by step.

    Within a step, sample_idx must run 0, 1, 2, ... in file order: a gap, repeat, or shuffle means the
    recording is incomplete or was re-sorted, and the replay would silently compute a different mean."""
    need = {"step", "setpoint_c", "sample_idx", "temp_cc", "acc_z"}
    groups: dict[tuple[int, int], tuple[list[int], list[int]]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or not need.issubset(reader.fieldnames):
            raise SystemExit(f"{path}: header must include {sorted(need)}")
        for n, row in enumerate(reader, start=2):
            try:
                step, sp, idx = int(row["step"]), int(row["setpoint_c"]), int(row["sample_idx"])
                temp, acc = int(row["temp_cc"]), int(row["acc_z"])
            except (TypeError, ValueError):
                raise SystemExit(f"{path}:{n}: non-integer value") from None
            if not (1 <= step <= 1000 and -200 <= sp <= 500):
                raise SystemExit(f"{path}:{n}: step/setpoint out of range")
            if temp not in INT16 or acc not in INT16:
                raise SystemExit(f"{path}:{n}: sample outside int16")
            temps, accs = groups.setdefault((step, sp), ([], []))
            if idx != len(temps):
                raise SystemExit(f"{path}:{n}: step {step} expected sample_idx {len(temps)}, got {idx}")
            temps.append(temp)
            accs.append(acc)
            if n - 1 > MAX_SAMPLE_ROWS:
                raise SystemExit(f"{path}: more than {MAX_SAMPLE_ROWS} rows")
    if not groups:
        raise SystemExit(f"{path}: no samples")
    return groups


def replay(samples_path: Path) -> list[StepResult]:
    """Offline path: the recorded raw samples stand in for Read Node Packet.vi; no waiting, no chamber."""
    groups = load_samples(samples_path)
    return [compute_step(step, sp, temps, accs) for (step, sp), (temps, accs) in sorted(groups.items())]


def write_results(path: Path, results: list[StepResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(RESULT_FIELDS)
        for r in results:
            w.writerow(r.as_row())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", type=Path, required=True, help="raw samples CSV logged by the LabVIEW rig")
    ap.add_argument("--out", type=Path, required=True, help="where to write the regenerated results table")
    a = ap.parse_args(argv)
    results = replay(a.replay)
    write_results(a.out, results)
    overall = all(r.verdict == "PASS" for r in results)
    print(f"{len(results)} steps -> {a.out}; overall {'PASS' if overall else 'FAIL'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
