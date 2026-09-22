---
name: matlab-to-code
description: Take a MATLAB function (.m) or Simulink model (.slx) to C or Python that matches it - read the math, write down the numeric semantics, export golden vectors, implement, and prove equivalence with bench_compare.py. Reviews existing generated code instead of replacing it.
argument-hint: "[path to .m or .slx] [--target c|python|both] [--vectors existing.csv]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

Model to code for: `$ARGUMENTS`.

## Where MATLAB sits

MATLAB/Simulink is where the algorithm is designed and proven on data. C is what ships on the target.
Python is the twin used for replay and test. This skill moves an algorithm from the first seat to the
other two **with evidence**, and it works without a MATLAB licence on the laptop: `.m` is text, `.slx` is
a zip of XML, and golden vectors are CSV.

If the team already runs Embedded Coder / MATLAB Coder, do **not** re-port the algorithm. Review the
generated C instead (step 5) and use the same vectors as a SIL-style check.

## Step 1 - Read the model

| Input | How to read it here | What to write down |
| --- | --- | --- |
| `.m` function | Open it; it is text | Signature, every constant, loop bounds, index arithmetic, integer types (`int16(...)`, `fi(...)`), rounding calls (`round`, `fix`, `floor`, `ceil`), saturation (`min/max`, `sat`), NaN/Inf handling |
| `.slx` model | `python -c "import zipfile,sys; print('\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))" model.slx` then read `simulink/systems/system_root.xml` (blocks, parameters, sample times) and `simulink/blockdiagram.xml` | Block list, data types per signal, sample time, saturation/overflow flags on Sum/Gain/Product, Rounding mode, Discrete Filter coefficients |
| `.slx` with a generated report or `.mdl` | Text; same as above | Same |
| Existing test vectors, `.mat` logs | `.mat` v7.3 is HDF5 (needs `h5py`); older `.mat` needs `scipy`. Ask for a CSV export from MATLAB instead: `writematrix([x y], 'vectors.csv')` | Golden inputs and outputs |
| MATLAB itself (the customer's machine) | `export_vectors.m` pattern in `example-system/model/` | Vectors with the edge cases from step 2 |

Write `outputs/<model>-notes.md` with the table from `example-system/model/MODEL-NOTES.md`: indexing,
warm-up, accumulator width, rounding, saturation, types in/out, and "where a naive port goes wrong".

## Step 2 - Numeric semantics checklist (this is where ports fail)

Check each line against the model and say what the C/Python will do.

- **Indexing**: MATLAB is 1-based inclusive `x(lo:k)`; C is 0-based. Warm-up windows are the usual off-by-one.
- **Integer division**: MATLAB `int16(-3)/int16(4)` rounds to nearest (`-1`); C and Python `//`-style
  truncation give `0` / `-1` respectively. Only `fix()` in MATLAB matches C `/` on ints.
- **`round()`**: MATLAB rounds half away from zero; Python `round()` is ties-to-even; C `lrint` follows the
  FPU mode. Never port `round` without a vector that hits `.5`.
- **Fixed point** (`fi`, Simulink data types): word length, fraction length, signedness, overflow
  (wrap vs saturate), rounding mode per block. Write the Q-format next to every signal.
- **Saturation**: does the model saturate or wrap? Simulink blocks have a checkbox; `.m` code usually has none.
- **Accumulator width**: a sum of `n` `int16` needs `int32`; say so and test the extreme.
- **Floating point**: `double` in MATLAB, maybe `float` on target. State the tolerance you will accept
  in `bench_compare --tol` and derive it from the model, not from "it passed".
- **NaN/Inf, empty input, first sample**: what does the model do, what will the code do.
- **Sample time**: the model's `Ts` is an assumption the firmware scheduler must honour; note it, cannot test it here.

## Step 3 - Golden vectors

Ask the model owner to export vectors that include: nominal data, negative values, type extremes
(`-32768`, `32767`), rounding-sensitive sums (the `.5` and negative-odd cases), warm-up (first `n`
samples), and saturation triggers. CSV with an index column and one column per input and output, as
`example-system/model/filter_vectors.csv` (`k, sample, filtered`). Fewer than 20 rows is not a vector set.

If no MATLAB is available, write the reference in Python from the `.m` (step 1 notes), generate the
vectors with it, and **label them "Python reference, not MATLAB-produced"** in the notes. That is a weaker
claim and the report must say so.

## Step 4 - Implement and prove

Python twin first, then C, same tests for both (see `/tdd`). Implementation goes where the code lives
(`example-system/src/`, `example-system/sim/`, or the customer's tree); vectors and the runner go next to
the model.

```bash
python example-system/model/run_vectors.py --impl python --out outputs/model-python.csv
python example-system/model/run_vectors.py --impl c      --out outputs/model-c.csv      # needs a C compiler
python tools/bench_compare.py example-system/model/filter_vectors.csv outputs/model-python.csv --markdown
```

Integer outputs: `--tol 0`. Float outputs: the tolerance from step 2, with the reason in the notes.
A unit test pins the vectors and the equivalence: `example-system/tests/test_model_equivalence.py`.

## Step 5 - When generated code already exists

Embedded Coder output is the customer's contract with their toolchain; review, do not rewrite.
Read the generated `.c/.h` for: the data types and rounding it chose (compare with step 2), `rtwtypes.h`
assumptions, saturation helpers, and the step function's call contract. Then run the **same vectors**
through the generated code with a small driver (pattern: `example-system/model/vectors_driver.c`) and
compare. Differences are findings for the model owner, not things to "fix" in generated code.

## What this does not prove

Vector equivalence checks the port, not the design: it says nothing about whether the algorithm meets the
requirement, about timing or scheduling on the target, about generated-code correctness beyond the vectors
supplied, or about behaviour on inputs the vectors did not include. Say this in the notes every time.

## Worked example

`/matlab-to-code example-system/model/moving_avg.m --target both`
Notes table filled in; `k = 10` (sum `-3`, window 4) kept because MATLAB integer division would give `-1`
and C gives `0`; 26 vectors; Python twin and C firmware both `PASS` exact; test suite pins it. Hand the
notes to `/design-artifacts` to update SN-REQ-003's verification line, and to `/exec-deck` if asked.
