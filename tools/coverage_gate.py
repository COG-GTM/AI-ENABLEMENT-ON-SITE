#!/usr/bin/env python3
"""Check changed tracked and untracked lines against an LCOV or Cobertura report."""

import argparse
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "coverage"


def decode_git_path(raw: str) -> str:
    value = raw.strip()
    if not value.startswith('"'):
        return value.split("\t", 1)[0]
    decoded = bytearray()
    index = 1
    escapes = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}
    while index < len(value):
        char = value[index]
        if char == '"':
            break
        if char != "\\":
            decoded.extend(char.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(value):
            break
        char = value[index]
        if char in "01234567":
            end = index + 1
            while end < min(index + 3, len(value)) and value[end] in "01234567":
                end += 1
            decoded.append(int(value[index:end], 8))
            index = end
        else:
            decoded.append(escapes.get(char, ord(char)))
            index += 1
    return decoded.decode("utf-8", errors="surrogateescape")


def quote_git_path(value: str) -> str:
    if not re.search(r'[\s"\\\x00-\x1f\x7f]', value):
        return value
    escapes = {"\a": r"\a", "\b": r"\b", "\t": r"\t", "\n": r"\n",
               "\v": r"\v", "\f": r"\f", "\r": r"\r", '"': r'\"', "\\": r"\\"}
    quoted = []
    for char in value:
        if char in escapes:
            quoted.append(escapes[char])
        elif ord(char) < 32 or ord(char) == 127:
            quoted.append(f"\\{ord(char):03o}")
        else:
            quoted.append(char)
    return '"' + "".join(quoted) + '"'


def parse_diff(text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current = None
    deleted = False
    new_line = 0
    in_hunk = False
    old_remaining = 0
    new_remaining = 0
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if in_hunk:
            if line == r"\ No newline at end of file":
                continue
            if line.startswith("+") and new_remaining > 0:
                if current and not deleted:
                    changed.setdefault(current, set()).add(new_line)
                new_line += 1
                new_remaining -= 1
            elif line.startswith("-") and old_remaining > 0:
                old_remaining -= 1
            elif line.startswith(" ") and old_remaining > 0 and new_remaining > 0:
                old_remaining -= 1
                new_remaining -= 1
                new_line += 1
            else:
                in_hunk = False
            if in_hunk and old_remaining == 0 and new_remaining == 0:
                in_hunk = False
            if in_hunk:
                continue
        if line.startswith("diff --git "):
            current, deleted, in_hunk = None, False, False
        elif line.startswith("rename to "):
            current = decode_git_path(line[len("rename to "):])
        elif line.startswith("deleted file mode "):
            deleted = True
        elif line.startswith("+++ "):
            path = decode_git_path(line[4:])
            if path == "/dev/null":
                deleted = True
            elif path.startswith("b/"):
                current = path[2:]
        elif line.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                new_line = int(match.group(2))
                old_remaining = int(match.group(1) or 1)
                new_remaining = int(match.group(3) or 1)
                in_hunk = True
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
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("threshold must be a finite number between 0 and 100")
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
        base = subprocess.run(
            ["git", "merge-base", args.base, "HEAD"],
            cwd=args.repo,
            capture_output=True,
            text=True,
        )
        if base.returncode:
            raise ValueError(f"git merge-base failed: {base.stderr.strip()}")
        proc = subprocess.run(
            ["git", "diff", "--unified=0", "--no-color", base.stdout.strip(), "--"],
            cwd=args.repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise ValueError(f"git diff failed: {proc.stderr.strip()}")
        diff = proc.stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=args.repo,
            capture_output=True,
        )
        if untracked.returncode:
            raise ValueError(f"git ls-files failed: {untracked.stderr.decode(errors='replace').strip()}")
        for raw_path in untracked.stdout.split(b"\0"):
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            source = Path(args.repo) / relative
            if not source.is_file() or source.is_symlink():
                continue
            lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                diff += (
                    f"diff --git a/{relative} b/{relative}\n"
                    f"--- /dev/null\n+++ {quote_git_path('b/' + relative)}\n"
                    f"@@ -0,0 +1,{len(lines)} @@\n"
                    + "".join(f"+{line}\n" for line in lines)
                )
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
    space_diff = parse_diff((FIXTURES / "space-path.diff").read_text(encoding="utf-8"))
    assert space_diff == {"src/My Component.ts": {1}}
    space_report = read_lcov(FIXTURES / "space-path.lcov", None)
    assert summarize(space_diff, space_report, 100.0)["covered"] == 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    inputs = ap.add_mutually_exclusive_group()
    inputs.add_argument("--lcov")
    inputs.add_argument("--cobertura")
    source = ap.add_mutually_exclusive_group()
    source.add_argument(
        "--base",
        help="diff merge-base(BASE, HEAD) against the working tree; staged/unstaged tracked edits and "
             "untracked non-ignored files are included (all untracked file lines count as added)",
    )
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
    if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 100:
        ap.error("--threshold must be a finite number between 0 and 100")
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
