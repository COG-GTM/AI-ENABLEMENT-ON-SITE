#!/usr/bin/env python3
"""Check coverage of added or modified lines against an LCOV or Cobertura report."""

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "coverage"


def parse_diff(text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current = None
    deleted = False
    new_line = 0
    in_hunk = False
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("diff --git "):
            current, deleted, in_hunk = None, False, False
        elif line.startswith("rename to "):
            current = line[len("rename to "):]
        elif line.startswith("deleted file mode "):
            deleted = True
        elif line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                deleted = True
            elif path.startswith("b/"):
                current = path[2:]
        elif line.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                new_line = int(match.group(2))
                in_hunk = True
            else:
                in_hunk = False
        elif in_hunk and current and not deleted:
            if line.startswith("+") and not line.startswith("+++"):
                changed.setdefault(current, set()).add(new_line)
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                continue
            elif line.startswith(" "):
                new_line += 1
            elif line == r"\ No newline at end of file":
                continue
            else:
                in_hunk = False
    return changed


def report_path(name: str, prefix: str | None) -> str:
    value = name.replace("\\", "/")
    if prefix:
        normalized = prefix.replace("\\", "/").rstrip("/")
        if normalized and value.startswith(normalized + "/"):
            value = value[len(normalized) + 1:]
        elif value == normalized:
            value = ""
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def read_lcov(path: Path, prefix: str | None) -> dict[str, dict[int, int]]:
    result: dict[str, dict[int, int]] = {}
    source = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("SF:"):
            source = report_path(line[3:], prefix)
            result.setdefault(source, {})
        elif source and line.startswith("DA:"):
            fields = line[3:].split(",")
            if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
                result[source][int(fields[0])] = int(fields[1])
        elif line == "end_of_record":
            source = None
    return result


def read_cobertura(path: Path, prefix: str | None) -> dict[str, dict[int, int]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"cannot parse Cobertura XML: {exc}") from exc
    result: dict[str, dict[int, int]] = {}
    for cls in root.iter("class"):
        name = cls.get("filename")
        if not name:
            continue
        source = report_path(name, prefix)
        lines = result.setdefault(source, {})
        for node in cls.findall("./lines/line"):
            number, hits = node.get("number"), node.get("hits")
            if number and hits and number.isdigit() and hits.isdigit():
                lines[int(number)] = int(hits)
    return result


def line_ranges(lines: list[int]) -> str:
    if not lines:
        return "none"
    spans = []
    first = previous = lines[0]
    for value in lines[1:]:
        if value != previous + 1:
            spans.append(f"{first}" if first == previous else f"{first}-{previous}")
            first = value
        previous = value
    spans.append(f"{first}" if first == previous else f"{first}-{previous}")
    return ", ".join(spans)


def summarize(changed: dict[str, set[int]], report: dict[str, dict[int, int]], threshold: float) -> dict:
    files = []
    for name in sorted(changed):
        measured = sorted(line for line in changed[name] if line in report.get(name, {}))
        uncovered = [line for line in measured if report[name][line] <= 0]
        covered = len(measured) - len(uncovered)
        percent = (covered * 100 / len(measured)) if measured else None
        files.append({
            "path": name,
            "changed_instrumented": len(measured),
            "covered": covered,
            "percent": percent,
            "uncovered_lines": uncovered,
            "uncovered_ranges": line_ranges(uncovered),
        })
    total = sum(item["changed_instrumented"] for item in files)
    covered = sum(item["covered"] for item in files)
    percent = (covered * 100 / total) if total else None
    return {
        "threshold": threshold,
        "changed_instrumented": total,
        "covered": covered,
        "percent": percent,
        "files": files,
        "pass": total == 0 or percent >= threshold,
        "note": "No measurable changed lines." if total == 0 else "",
    }


def markdown(summary: dict) -> str:
    lines = ["# Changed-line coverage gate", ""]
    if summary["changed_instrumented"] == 0:
        lines.extend([summary["note"], ""])
    else:
        lines.extend([
            f"Overall: **{summary['covered']}/{summary['changed_instrumented']} "
            f"({summary['percent']:.2f}%)**; threshold **{summary['threshold']:.2f}%**; "
            f"result **{'PASS' if summary['pass'] else 'FAIL'}**.",
            "",
            "| File | Changed instrumented | Covered | Coverage | Uncovered lines |",
            "| --- | ---: | ---: | ---: | --- |",
        ])
        for item in summary["files"]:
            pct = "no measurable lines" if item["percent"] is None else f"{item['percent']:.2f}%"
            lines.append(f"| `{item['path']}` | {item['changed_instrumented']} | {item['covered']} | {pct} | {item['uncovered_ranges']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def load_inputs(args) -> tuple[dict[str, set[int]], dict[str, dict[int, int]]]:
    if args.diff_file:
        diff = Path(args.diff_file).read_text(encoding="utf-8-sig")
    else:
        if not args.base:
            raise ValueError("--base is required when --diff-file is not supplied")
        proc = subprocess.run(
            ["git", "diff", "--unified=0", "--no-color", f"{args.base}...HEAD"],
            cwd=args.repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise ValueError(f"git diff failed: {proc.stderr.strip()}")
        diff = proc.stdout
    changed = parse_diff(diff)
    if args.lcov:
        report = read_lcov(Path(args.lcov), args.path_prefix)
    elif args.cobertura:
        report = read_cobertura(Path(args.cobertura), args.path_prefix)
    else:
        raise ValueError("one of --lcov or --cobertura is required")
    return changed, report


def check() -> None:
    diff = parse_diff((FIXTURES / "sample.diff").read_text(encoding="utf-8"))
    report = read_lcov(FIXTURES / "lcov.info", None)
    result = summarize(diff, report, 80.0)
    assert result["changed_instrumented"] == 5 and result["covered"] == 4 and result["percent"] == 80.0
    cobertura = read_cobertura(FIXTURES / "cobertura.xml", None)
    assert summarize(diff, cobertura, 80.0)["covered"] == 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    inputs = ap.add_mutually_exclusive_group()
    inputs.add_argument("--lcov")
    inputs.add_argument("--cobertura")
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--base")
    source.add_argument("--diff-file")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--threshold", type=float, default=80.0)
    ap.add_argument("--path-prefix")
    ap.add_argument("--out", default="outputs/coverage-gate.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        try:
            check()
            print("coverage_gate --check: OK")
            return 0
        except (AssertionError, OSError, ValueError) as exc:
            print(f"coverage_gate --check: {exc}", file=sys.stderr)
            return 2
    if not 0 <= args.threshold <= 100:
        ap.error("--threshold must be between 0 and 100")
    if not (args.lcov or args.cobertura):
        ap.error("one of --lcov or --cobertura is required")
    try:
        changed, report = load_inputs(args)
        summary = summarize(changed, report, args.threshold)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown(summary), encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"coverage_gate: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{summary['covered']}/{summary['changed_instrumented']} changed lines covered; "
              f"{'PASS' if summary['pass'] else 'FAIL'} ({summary['threshold']:.2f}% threshold)")
    return 0 if summary["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
