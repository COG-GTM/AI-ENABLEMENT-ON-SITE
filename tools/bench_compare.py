#!/usr/bin/env python3
"""Compare a recorded CSV (the reference: a LabVIEW rig log, a MATLAB vector export, a bench capture)
with a CSV produced by code (a Python port, a C build) and say, per column, whether they agree.

Usage:
    python tools/bench_compare.py expected.csv actual.csv                        # exact match required
    python tools/bench_compare.py expected.csv actual.csv --tol mean_temp_cc=1   # abs tolerance per column
    python tools/bench_compare.py expected.csv actual.csv --tol '*=0.05'         # default tolerance for every numeric column
    python tools/bench_compare.py expected.csv actual.csv --markdown > outputs/rig-compare.md
    python tools/bench_compare.py expected.csv actual.csv --json

Rules:
  - Both files need a header row and at least one data row; a header-only file is bad input, not a PASS.
    Columns are matched by name; order does not matter.
  - A column present in only one file is reported (missing / extra) and fails the run.
  - Row counts must match; the report gives the first row where a column diverges.
  - A cell that parses as a number in both files is compared numerically in decimal arithmetic, so
    `9007199254740993` and `9007199254740992` differ, as do `0.1` and `0.10000000000000001`. Exact when
    no tolerance is set, otherwise |a - b| <= tol; anything else is compared as text after stripping
    whitespace. NaN, infinity, and magnitudes outside about 1e-300..1e300 (not a measurement) never pass.
  - Report figures (tolerance, max abs error) are rounded to doubles; the PASS/FAIL decision is not. Max abs
    error is `-` (JSON null) for text columns and when a cell is NaN, infinite, or out of range; the first
    divergence names the cell.
  - Exit 0 = every column PASS, 2 = at least one FAIL, 1 = bad input.

Standard library only; no network. The recorded file is never modified.
"""

import argparse
import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 1_000_000
MAX_COLUMNS = 512
MAX_NUMBER_CHARS = 64  # longer than any sane CSV number; keeps Decimal parsing bounded
MAX_EXPONENT = 300  # |decimal exponent| bound: keeps subtraction exact, never under/overflows, and report doubles finite
COLUMN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .:/()\[\]-]{0,63}$")
TOL_RE = re.compile(r"^(\*|[A-Za-z0-9_][A-Za-z0-9_ .:/()\[\]-]{0,63})=([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)$")


class CompareError(ValueError):
    """Bad input: unreadable file, malformed header, bad tolerance spec."""


def read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise CompareError(f"{path}: not a file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise CompareError(f"{path}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MB; split it first")
    with path.open(newline="", encoding="utf-8-sig", errors="strict") as fh:
        try:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                raise CompareError(f"{path}: empty file or missing header row")
            header = [h.strip() for h in header]
            if len(header) > MAX_COLUMNS:
                raise CompareError(f"{path}: more than {MAX_COLUMNS} columns")
            bad = [h for h in header if not COLUMN_RE.match(h)]
            if bad:
                raise CompareError(f"{path}: column names must be plain identifiers, got {bad[:3]!r}")
            if len(set(header)) != len(header):
                raise CompareError(f"{path}: duplicate column names in header")
            rows = []
            for n, raw in enumerate(reader, start=2):
                if not raw or all(not c.strip() for c in raw):
                    continue  # blank line
                if len(raw) != len(header):
                    raise CompareError(f"{path}:{n}: expected {len(header)} cells, got {len(raw)}")
                rows.append(dict(zip(header, (c.strip() for c in raw))))
                if len(rows) > MAX_ROWS:
                    raise CompareError(f"{path}: more than {MAX_ROWS} rows")
        except (csv.Error, UnicodeDecodeError) as e:
            raise CompareError(f"{path}: not readable as UTF-8 CSV ({type(e).__name__})") from e
    if not rows:
        raise CompareError(f"{path}: header only, no data rows; nothing to compare")
    return header, rows


def parse_tolerances(specs: list[str]) -> dict[str, Decimal]:
    tol: dict[str, Decimal] = {}
    for s in specs:
        m = TOL_RE.match(s.strip())
        if not m:
            raise CompareError(f"bad --tol {s!r}; use column=number (e.g. temp_c=0.05) or '*=0.05'")
        value = as_number(m.group(2))
        if value is None or not in_range(value) or value < 0:
            raise CompareError(f"bad --tol {s!r}; tolerance must be 0 or a number in 1e-{MAX_EXPONENT}..1e{MAX_EXPONENT}")
        tol[m.group(1)] = value
    return tol


def as_number(text: str) -> Decimal | None:
    """Decimal, so exact mode is exact: floats would merge 2**53 and 2**53 + 1. None if not a number."""
    if len(text) > MAX_NUMBER_CHARS:
        return None
    try:
        return Decimal(text)  # accepts nan/inf spellings too; the caller decides
    except InvalidOperation:
        return None


def in_range(v: Decimal) -> bool:
    """Finite and either zero or with a decimal exponent within +-MAX_EXPONENT."""
    return v.is_finite() and (v.is_zero() or abs(v.adjusted()) <= MAX_EXPONENT)


def compare_cell(expected: str, actual: str, tol: Decimal) -> tuple[bool, Decimal | None]:
    """Return (match, abs_error). abs_error is None for text cells."""
    e, a = as_number(expected), as_number(actual)
    if e is None or a is None:
        return expected == actual, None
    if not (in_range(e) and in_range(a)):
        return False, Decimal("Infinity")
    if tol == 0:
        match = e == a  # exact mode never subtracts, so nothing can round or underflow to zero
    else:
        match = None
    with localcontext() as ctx:
        # operands are bounded (MAX_NUMBER_CHARS digits, |exponent| <= MAX_EXPONENT), so with this
        # precision the difference is exact to the digit and well inside the context's Emin/Emax
        ctx.prec = 2 * (MAX_NUMBER_CHARS + MAX_EXPONENT)
        err = abs(e - a)
        if match is None:
            match = err <= tol
    return match, err


def compare(expected_path: Path, actual_path: Path, tolerances: dict[str, Decimal | float | int]) -> dict:
    tolerances = {k: v if isinstance(v, Decimal) else Decimal(str(v)) for k, v in tolerances.items()}
    bad_tol = [k for k, v in tolerances.items() if not in_range(v) or v < 0]
    if bad_tol:
        raise CompareError(f"tolerance must be 0 or a number in 1e-{MAX_EXPONENT}..1e{MAX_EXPONENT}: {bad_tol[:3]!r}")
    exp_header, exp_rows = read_table(expected_path)
    act_header, act_rows = read_table(actual_path)
    missing = [c for c in exp_header if c not in act_header]
    extra = [c for c in act_header if c not in exp_header]
    shared = [c for c in exp_header if c in act_header]
    unknown_tol = [c for c in tolerances if c != "*" and c not in exp_header and c not in act_header]
    default_tol = tolerances.get("*", Decimal(0))
    n = min(len(exp_rows), len(act_rows))
    columns = []
    for col in shared:
        tol = tolerances.get(col, default_tol)
        mismatches, max_err, first_bad, numeric = 0, Decimal(0), None, True
        for i in range(n):
            ok, err = compare_cell(exp_rows[i][col], act_rows[i][col], tol)
            if err is None:
                numeric = False
            elif err > max_err:
                max_err = err
            if not ok:
                mismatches += 1
                if first_bad is None:
                    first_bad = {"row": i + 2, "expected": exp_rows[i][col], "actual": act_rows[i][col]}
        columns.append({
            "column": col,
            "kind": "numeric" if numeric else "text",
            "tolerance": float(tol),
            "rows": n,
            "mismatches": mismatches,
            "max_abs_error": float(max_err) if numeric and max_err.is_finite() else None,
            "first_divergence": first_bad,
            "pass": mismatches == 0,
        })
    row_count_ok = len(exp_rows) == len(act_rows)
    problems = []
    if missing:
        problems.append(f"missing in actual: {', '.join(missing)}")
    if extra:
        problems.append(f"extra in actual: {', '.join(extra)}")
    if not row_count_ok:
        problems.append(f"row count differs: expected {len(exp_rows)}, actual {len(act_rows)}")
    if unknown_tol:
        problems.append(f"--tol names unknown column(s): {', '.join(unknown_tol)}")
    verdict = "PASS" if row_count_ok and not missing and not extra and not unknown_tol and all(c["pass"] for c in columns) else "FAIL"
    return {
        "expected": str(expected_path),
        "actual": str(actual_path),
        "rows_expected": len(exp_rows),
        "rows_actual": len(act_rows),
        "columns": columns,
        "missing_columns": missing,
        "extra_columns": extra,
        "problems": problems,
        "verdict": verdict,
    }


def fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.6g}"


def render_text(r: dict) -> str:
    w = max([len(c["column"]) for c in r["columns"]] + [6])
    lines = [f"expected {r['expected']} ({r['rows_expected']} rows) vs actual {r['actual']} ({r['rows_actual']} rows)", ""]
    lines.append(f"{'column':<{w}}  {'kind':<7} {'tol':>8}  {'max err':>10}  {'bad rows':>8}  result  first divergence")
    for c in r["columns"]:
        fd = c["first_divergence"]
        where = f"row {fd['row']}: expected {fd['expected']!r}, got {fd['actual']!r}" if fd else ""
        lines.append(f"{c['column']:<{w}}  {c['kind']:<7} {fmt(c['tolerance']):>8}  {fmt(c['max_abs_error']):>10}  "
                     f"{c['mismatches']:>8}  {'PASS' if c['pass'] else 'FAIL':<6}  {where}")
    for p in r["problems"]:
        lines.append(f"problem: {p}")
    lines.append(f"\n-> {r['verdict']}")
    return "\n".join(lines)


def render_markdown(r: dict) -> str:
    lines = ["# Bench comparison", "",
             f"Expected: `{r['expected']}` ({r['rows_expected']} rows). Actual: `{r['actual']}` ({r['rows_actual']} rows).", "",
             "| Column | Kind | Tolerance | Max abs error | Rows differing | Result | First divergence |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in r["columns"]:
        fd = c["first_divergence"]
        where = f"row {fd['row']}: expected `{fd['expected']}`, got `{fd['actual']}`" if fd else ""
        lines.append(f"| `{c['column']}` | {c['kind']} | {fmt(c['tolerance'])} | {fmt(c['max_abs_error'])} | "
                     f"{c['mismatches']} / {c['rows']} | {'PASS' if c['pass'] else 'FAIL'} | {where} |")
    if r["problems"]:
        lines += ["", "Problems:", ""] + [f"- {p}" for p in r["problems"]]
    lines += ["", f"-> **{r['verdict']}**"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("expected", type=Path, help="recorded / reference CSV")
    ap.add_argument("actual", type=Path, help="CSV produced by the code under test")
    ap.add_argument("--tol", action="append", default=[], metavar="COL=N", help="absolute tolerance for a numeric column; '*=N' sets the default")
    fmt_group = ap.add_mutually_exclusive_group()
    fmt_group.add_argument("--markdown", action="store_true")
    fmt_group.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        result = compare(a.expected, a.actual, parse_tolerances(a.tol))
    except CompareError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(result, indent=2, allow_nan=False))
    elif a.markdown:
        print(render_markdown(result), end="")
    else:
        print(render_text(result))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
