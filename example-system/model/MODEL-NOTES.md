# Model notes: `moving_avg.m` → `src/filter.c` / `sim/sensor_node/filter.py`

What `/matlab-to-code` produces for a real model. This one is small on purpose so the notes fit on
a page; the headings are the ones the skill fills in every time.

## What the model computes

Sliding mean of the last 4 samples (SN-REQ-003). Output is an integer.

| Aspect | MATLAB (`moving_avg.m`) | C / Python twins | Watch for |
| --- | --- | --- | --- |
| Indexing | `x(lo:k)`, 1-based inclusive | ring buffer `buf[head]`, 0-based | off-by-one in warm-up |
| Warm-up | average of `k` samples until `k >= n` | `count` grows to `FILTER_WINDOW` | dividing by 4 too early |
| Accumulator | `double` | `int32_t` sum | `4 * 32767` overflows `int16` |
| Rounding | `fix(sum / count)` (toward zero) | C `/` on `int32_t` (toward zero); Python `int(sum / count)` | MATLAB `int16` division rounds to nearest |
| Saturation | none needed: result is within input range | none | a filter with gain would need it |
| Types in/out | `int16` in, `int16` out | `int16_t` / Python `int` bounded by tests | silently widening in Python |

## Where a naive port goes wrong

`int16(-3) / int16(4)` is `-1` in MATLAB (round to nearest). C gives `0`. If the model had been
written with integer division instead of `fix()`, the model and the firmware would disagree
whenever a negative sum does not divide evenly. Row `k = 10` of `filter_vectors.csv` (sum `-3`,
window 4) is that case; `tests/test_model_equivalence.py` asserts it stays in the vector set.

## Golden vectors

`filter_vectors.csv` has 26 rows, one filter stream, columns `k, sample, filtered`. Written by
`export_vectors.m` in MATLAB; replayed here without MATLAB:

```bash
python example-system/model/run_vectors.py --impl python --out outputs/model-python.csv
python example-system/model/run_vectors.py --impl c      --out outputs/model-c.csv      # optional, needs cc
python tools/bench_compare.py example-system/model/filter_vectors.csv outputs/model-python.csv
```

Tolerance is exact (`0`) because the output is an integer. A floating-point model would set
`--tol filtered=<n>` from the model's own numeric analysis, and say why.

## What this does not prove

- That the model is the right algorithm for the requirement. Vectors check the port, not the design.
- Timing, sample-rate, or scheduling behaviour on the target.
- Anything about Simulink-generated C (Embedded Coder); when that exists, review it, do not re-port it.
