#!/usr/bin/env python3
"""Requirement -> hazard -> test -> tracker traceability matrix.

    python tools/trace_matrix.py                       # Markdown table to stdout
    python tools/trace_matrix.py --json                # machine-readable
    python tools/trace_matrix.py --out outputs/trace-matrix.md
    python tools/trace_matrix.py --system ../my-firmware   # same layout: docs/SRS.md, docs/HAZARDS.md, tests/, tracker.json

Reads the SRS and hazard tables, scans every test file for requirement IDs, and joins the tracker.
Exit 1 when a requirement has no test and no analysis artifact, a `test_name` in "Verified by" does
not exist, a hazard with risk >= 8 has no mitigation requirement, or an Open hazard has no tracker
item. Standard library only; never touches the network.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSTEM = ROOT / "example-system"

REQ_RE = re.compile(r"\b[A-Z]{2,6}-REQ-\d{3}\b")
HAZ_RE = re.compile(r"\b[A-Z]{2,6}-HAZ-\d{3}\b")
ROW_RE = re.compile(r"^\|\s*([A-Z]{2,6}-(?:REQ|HAZ)-\d{3})\s*\|(.*)\|\s*$")
PY_TEST_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(")
C_TEST_RE = re.compile(r"^\s*(?:static\s+)?void\s+(test_\w+)\s*\(")
NAMED_TEST_RE = re.compile(r"`(test_\w+)`")
ANALYSIS_HINTS = ("review", "analysis", "inspection", ".md", "make test")
HIGH_RISK = 8


HEADER_RE = re.compile(r"^\|(.+)\|\s*$")
RULE_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+\s*$")


def cells(rest: str) -> list[str]:
    return [c.strip() for c in rest.strip().strip("|").split("|")]


def table_rows(path: Path, kind: str) -> list[dict[str, str]]:
    """Every table row whose first cell is a <kind> ID, as {column name (lower) -> cell}.
    Columns are matched by the header row above them, so column order and extra columns do not matter."""
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    prev = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if RULE_RE.match(line) and HEADER_RE.match(prev):
            headers = [h.lower() for h in cells(prev)]
        else:
            m = ROW_RE.match(line)
            if m and f"-{kind}-" in m.group(1) and headers:
                c = [m.group(1)] + cells(m.group(2))
                row = {h: (c[i] if i < len(c) else "") for i, h in enumerate(headers)}
                row["_id"] = m.group(1)
                rows.append(row)
        prev = line
    return rows


def col(row: dict[str, str], *names: str) -> str:
    """Cell under the first header that equals, then contains, one of the names."""
    for n in names:
        if n in row:
            return row[n]
    for n in names:
        for h, v in row.items():
            if n in h:
                return v
    return ""


def read_requirements(srs: Path) -> dict[str, dict]:
    reqs = {}
    for row in table_rows(srs, "REQ"):
        rid = row["_id"]
        reqs[rid] = {"id": rid, "text": col(row, "requirement", "text"), "priority": col(row, "priority"),
                     "verified_by": col(row, "verified", "verification"),
                     "hazards": [], "tests": {"python": [], "c": []}, "tracker": []}
    return reqs


def read_hazards(path: Path) -> dict[str, dict]:
    hazards = {}
    if not path.exists():
        return hazards
    for row in table_rows(path, "HAZ"):
        hid = row["_id"]
        try:
            risk = int(col(row, "risk", "rpn"))
        except ValueError:
            risk = 0
        hazards[hid] = {"id": hid, "failure_mode": col(row, "failure", "hazard"), "risk": risk,
                        "requirements": sorted(set(REQ_RE.findall(col(row, "mitigation", "control")))),
                        "verified_by": col(row, "verified", "verification"), "status": col(row, "status"), "tracker": []}
    return hazards


def scan_tests(tests_dir: Path) -> tuple[dict[str, dict[str, list[str]]], set[str]]:
    """Returns (requirement ID -> {"python": [file::test, ...], "c": [...]}, all test names).
    Test names are function names plus file stems, so `test_packet` may mean tests/test_packet.py.
    A requirement named in a file's header (before the first test) is attributed to the whole file."""
    found: dict[str, dict[str, list[str]]] = {}
    names: set[str] = set()
    for f in sorted(tests_dir.rglob("*")):
        if f.suffix not in (".py", ".c") or not f.name.startswith("test"):
            continue
        twin = "python" if f.suffix == ".py" else "c"
        name_re = PY_TEST_RE if twin == "python" else C_TEST_RE
        current = None
        rel = f.relative_to(tests_dir.parent).as_posix()
        names.add(f.stem)
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = name_re.match(line)
            if m:
                current = m.group(1)
                names.add(current)
            for rid in REQ_RE.findall(line):
                label = f"{rel}::{current}" if current else rel
                bucket = found.setdefault(rid, {"python": [], "c": []})[twin]
                if label not in bucket:
                    bucket.append(label)
    return found, names


def read_tracker(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    return [i for i in items if isinstance(i, dict) and "id" in i]


def build(system: Path) -> dict:
    reqs = read_requirements(system / "docs" / "SRS.md")
    hazards = read_hazards(system / "docs" / "HAZARDS.md")
    tests, test_names = scan_tests(system / "tests")
    tracker = read_tracker(system / "tracker.json")
    problems: list[str] = []

    for r in reqs.values():
        for name in NAMED_TEST_RE.findall(r["verified_by"]):
            if name not in test_names:
                problems.append(f"{r['id']} says verified by `{name}` but no such test exists")

    for rid, t in tests.items():
        if rid in reqs:
            reqs[rid]["tests"] = t
        else:
            problems.append(f"{rid} appears in tests but not in SRS.md")
    for h in hazards.values():
        for rid in h["requirements"]:
            if rid in reqs:
                reqs[rid]["hazards"].append(h["id"])
            else:
                problems.append(f"{h['id']} mitigates {rid} which is not in SRS.md")
        if h["risk"] >= HIGH_RISK and not h["requirements"]:
            problems.append(f"{h['id']} has risk {h['risk']} but no mitigation requirement")
    for it in tracker:
        for rid in it.get("requirements", []):
            if rid in reqs:
                reqs[rid]["tracker"].append(it["id"])
            else:
                problems.append(f"{it['id']} references {rid} which is not in SRS.md")
        for hid in it.get("hazards", []):
            if hid in hazards:
                hazards[hid]["tracker"].append(it["id"])
            else:
                problems.append(f"{it['id']} references {hid} which is not in HAZARDS.md")
    for h in hazards.values():
        if h["status"].lower().startswith("open") and not h["tracker"]:
            problems.append(f"{h['id']} is Open but no tracker item references it")

    for r in reqs.values():
        n_py, n_c = len(r["tests"]["python"]), len(r["tests"]["c"])
        if n_py or n_c:
            r["verdict"] = "tested" if (n_py and n_c) else "tested (one twin)"
        elif any(k in r["verified_by"].lower() for k in ANALYSIS_HINTS):
            r["verdict"] = "analysis"
        else:
            r["verdict"] = "UNTESTED"
            problems.append(f"{r['id']} has no test and no analysis artifact")

    counts = {"requirements": len(reqs), "hazards": len(hazards), "tracker_items": len(tracker),
              "tested": sum(r["verdict"].startswith("tested") for r in reqs.values()),
              "analysis": sum(r["verdict"] == "analysis" for r in reqs.values()),
              "untested": sum(r["verdict"] == "UNTESTED" for r in reqs.values())}
    return {"system": str(system), "counts": counts, "requirements": list(reqs.values()),
            "hazards": list(hazards.values()), "problems": problems}


def to_markdown(m: dict) -> str:
    c = m["counts"]
    out = ["# Traceability matrix", "",
           f"{c['requirements']} requirements: {c['tested']} tested, {c['analysis']} by analysis, "
           f"{c['untested']} untested. {c['hazards']} hazards, {c['tracker_items']} tracker items.", "",
           "| Requirement | Priority | Hazards | Python tests | C tests | Tracker | Verdict |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in m["requirements"]:
        py = ", ".join(t.split("::")[-1] for t in r["tests"]["python"]) or "-"
        cc = ", ".join(t.split("::")[-1] for t in r["tests"]["c"]) or "-"
        out.append(f"| {r['id']} | {r['priority']} | {', '.join(r['hazards']) or '-'} | {py} | {cc} | "
                   f"{', '.join(r['tracker']) or '-'} | {r['verdict']} |")
    out += ["", "| Hazard | Risk | Mitigated by | Status | Tracker |", "| --- | --- | --- | --- | --- |"]
    for h in m["hazards"]:
        out.append(f"| {h['id']} | {h['risk']} | {', '.join(h['requirements']) or '-'} | {h['status']} | "
                   f"{', '.join(h['tracker']) or '-'} |")
    if m["problems"]:
        out += ["", "## Problems", ""] + [f"- {p}" for p in m["problems"]]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", type=Path, default=DEFAULT_SYSTEM, help="directory with docs/, tests/, tracker.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, help="write here instead of stdout")
    a = ap.parse_args(argv)
    srs = a.system / "docs" / "SRS.md"
    if not srs.exists():
        print(f"error: {srs} not found", file=sys.stderr)
        return 1
    m = build(a.system)
    text = json.dumps(m, indent=2) + "\n" if a.json else to_markdown(m)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        sys.stdout.write(text)
    if m["problems"]:
        for p in m["problems"]:
            print(f"problem: {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
