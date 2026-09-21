#!/usr/bin/env python3
"""Summarise example-system/tracker.json as a status report.

Usage:
    python tools/tracker_report.py                       # text summary
    python tools/tracker_report.py --markdown            # Markdown report
    python tools/tracker_report.py --json                # machine-readable, used by build_deck.py
    python tools/tracker_report.py --file other.json     # any file with the same schema

Validates every item against the schema in templates/tracker-item.json (required keys, enums, ID pattern).
Standard library only.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "example-system" / "tracker.json"
SCHEMA = ROOT / "templates" / "tracker-item.json"

ID_RE = re.compile(r"^[A-Z]{2,6}-(BUG|CAP)-\d{3}$")
OPEN_STATES = ("proposed", "open", "in_review")
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load(path: Path):
    data = json.loads(path.read_text())
    schema = json.loads(SCHEMA.read_text())
    items = data["items"]
    errors = []
    seen = set()
    for it in items:
        for key in schema["required"]:
            if key not in it:
                errors.append(f"{it.get('id', '?')}: missing {key}")
        if not ID_RE.match(it.get("id", "")):
            errors.append(f"{it.get('id', '?')}: id must match {ID_RE.pattern}")
        if it.get("id") in seen:
            errors.append(f"{it['id']}: duplicate id")
        seen.add(it.get("id"))
        for key in ("type", "severity", "status"):
            allowed = schema["properties"][key]["enum"]
            if it.get(key) not in allowed:
                errors.append(f"{it.get('id', '?')}: {key}={it.get(key)!r} not in {allowed}")
        if len(str(it.get("title", ""))) > 120:
            errors.append(f"{it.get('id')}: title over 120 chars")
    if errors:
        raise SystemExit("tracker validation failed:\n  " + "\n  ".join(errors))
    return items


def summarise(items):
    open_items = [i for i in items if i["status"] in OPEN_STATES]
    closed = [i for i in items if i["status"] == "closed"]
    top = sorted(open_items, key=lambda i: (SEV_ORDER[i["severity"]], i["opened"]))
    return {
        "total": len(items),
        "open": len(open_items),
        "closed": len(closed),
        "by_type": dict(Counter(i["type"] for i in items)),
        "by_status": dict(Counter(i["status"] for i in items)),
        "open_by_severity": dict(Counter(i["severity"] for i in open_items)),
        "open_by_component": dict(Counter(i["component"] for i in open_items)),
        "hazards_with_open_items": sorted({h for i in open_items for h in i["hazards"]}),
        "requirements_with_open_items": sorted({r for i in open_items for r in i["requirements"]}),
        "top_open": [{k: i[k] for k in ("id", "type", "severity", "status", "title", "component")} for i in top[:5]],
    }


def render_markdown(s):
    out = ["# Tracker status report", ""]
    out.append(f"- Items: {s['total']} total, {s['open']} open, {s['closed']} closed")
    out.append("- Open by severity: " + ", ".join(f"{k} {v}" for k, v in sorted(s["open_by_severity"].items(), key=lambda kv: SEV_ORDER[kv[0]])))
    out.append("- Open by component: " + ", ".join(f"{k} {v}" for k, v in sorted(s["open_by_component"].items())))
    out.append("- Hazards with open work: " + (", ".join(s["hazards_with_open_items"]) or "none"))
    out.append("")
    out.append("## Top open items")
    out.append("")
    out.append("| ID | Type | Severity | Status | Component | Title |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for i in s["top_open"]:
        out.append(f"| {i['id']} | {i['type']} | {i['severity']} | {i['status']} | {i['component']} | {i['title']} |")
    return "\n".join(out)


def render_text(s):
    lines = [f"{s['total']} items: {s['open']} open, {s['closed']} closed"]
    lines.append("open by severity: " + json.dumps(s["open_by_severity"]))
    lines.append("open by component: " + json.dumps(s["open_by_component"]))
    lines.append("top open:")
    for i in s["top_open"]:
        lines.append(f"  {i['id']:<11} {i['severity']:<8} {i['status']:<10} {i['title']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=DEFAULT)
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--markdown", action="store_true")
    fmt.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    s = summarise(load(a.file))
    if a.json:
        print(json.dumps(s, indent=2))
    elif a.markdown:
        print(render_markdown(s))
    else:
        print(render_text(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
