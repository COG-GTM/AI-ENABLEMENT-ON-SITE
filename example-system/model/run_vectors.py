#!/usr/bin/env python3
"""Replay the model's golden vectors through a firmware twin and write what it produced.

    python example-system/model/run_vectors.py --impl python --out outputs/model-python.csv
    python example-system/model/run_vectors.py --impl c      --out outputs/model-c.csv   # needs cc
    python tools/bench_compare.py example-system/model/filter_vectors.csv outputs/model-python.csv

Reads filter_vectors.csv (k, sample, filtered) next to this file, feeds the samples in order to
the chosen implementation, and writes the same three columns with the implementation's output in
`filtered`. bench_compare.py then says whether model and code agree, row by row. Exit 1 on bad
input or a failed C build. Standard library only.
"""

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
VECTORS = HERE / "filter_vectors.csv"
MAX_ROWS = 100_000
sys.path.insert(0, str(SYSTEM / "sim"))

from sensor_node.filter import MovingAverage  # noqa: E402


def load_samples(path: Path = VECTORS) -> list[int]:
    samples = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "sample" not in reader.fieldnames:
            raise SystemExit(f"{path}: needs a header with a 'sample' column")
        for n, row in enumerate(reader, start=2):
            try:
                v = int(row["sample"])
            except (TypeError, ValueError):
                raise SystemExit(f"{path}:{n}: sample is not an integer: {row.get('sample')!r}") from None
            if not -32768 <= v <= 32767:
                raise SystemExit(f"{path}:{n}: sample {v} outside int16")
            samples.append(v)
            if len(samples) > MAX_ROWS:
                raise SystemExit(f"{path}: more than {MAX_ROWS} rows")
    if not samples:
        raise SystemExit(f"{path}: no samples")
    return samples


def run_python(samples: list[int], window: int = 4) -> list[int]:
    f = MovingAverage(window)
    return [f.update(s) for s in samples]


def run_c(samples: list[int]) -> list[int]:
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        raise SystemExit("no C compiler (cc/gcc/clang) on PATH; use --impl python")
    build = SYSTEM / "build"
    build.mkdir(exist_ok=True)
    exe = build / "vectors_driver"
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-o", str(exe), str(HERE / "vectors_driver.c"), str(SYSTEM / "src" / "filter.c")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"C build failed:\n{r.stderr[-800:]}")
    r = subprocess.run([str(exe)], input="".join(f"{s}\n" for s in samples), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"C driver failed:\n{r.stderr[-800:]}")
    out = [int(x) for x in r.stdout.split()]
    if len(out) != len(samples):
        raise SystemExit(f"C driver returned {len(out)} values for {len(samples)} samples")
    return out


def write_csv(path: Path, samples: list[int], filtered: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["k", "sample", "filtered"])
        for k, (s, f) in enumerate(zip(samples, filtered), start=1):
            w.writerow([k, s, f])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--impl", choices=["python", "c"], default="python")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--vectors", type=Path, default=VECTORS)
    a = ap.parse_args(argv)
    samples = load_samples(a.vectors)
    filtered = run_python(samples) if a.impl == "python" else run_c(samples)
    write_csv(a.out, samples, filtered)
    print(f"{a.impl}: {len(samples)} samples -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
