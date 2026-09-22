#!/usr/bin/env python3
"""Turn a structured research JSON file into a one-page brief (Markdown and/or HTML).

Usage:
    python tools/research_brief.py templates/research-brief-example.json outputs/brief.md
    python tools/research_brief.py my-research.json outputs/brief.html
    python tools/research_brief.py --check                # validate the example only

Why a tool: it enforces that every finding cites at least one listed source, every source has a
location and a date, and confidence is one of high/medium/low. Devin does the research; this keeps
the write-up honest and consistent. Standard library only.

Input format (see templates/research-brief-example.json):
{
  "question": "...", "audience": "...", "date": "YYYY-MM-DD", "author": "role, not a person",
  "sources": [{"id": "S1", "title": "...", "location": "file path or URL", "date": "YYYY-MM-DD", "type": "repo|doc|web|interview|data"}],
  "findings": [{"claim": "...", "sources": ["S1"], "confidence": "high|medium|low", "note": "optional"}],
  "open_questions": ["..."],
  "recommendation": "...",
  "next_steps": ["..."]
}
"""

import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "templates" / "research-brief-example.json"
CONF = ("high", "medium", "low")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCE_ID_RE = re.compile(r"^S\d{1,3}$")


def valid_date(s) -> bool:
    """True for a real calendar date written as YYYY-MM-DD."""
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def md_cell(s) -> str:
    """Make free text safe inside a Markdown table cell."""
    return (
        str(s)
        .replace("\\", "\\\\")  # first, so a pre-existing backslash cannot neutralise the pipe escape below
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def validate(b: dict) -> list[str]:
    errs = []
    for key in ("question", "audience", "date", "author", "sources", "findings", "open_questions", "recommendation", "next_steps"):
        if key not in b:
            errs.append(f"missing top-level key {key!r}")
    if errs:
        return errs
    if not valid_date(b["date"]):
        errs.append("date must be a real calendar date written YYYY-MM-DD")
    ids = set()
    for s in b["sources"]:
        sid = s.get("id", "")
        if not SOURCE_ID_RE.match(sid):
            errs.append(f"source id {sid!r} must look like S1")
        if sid in ids:
            errs.append(f"duplicate source id {sid}")
        ids.add(sid)
        for k in ("title", "location", "date", "type"):
            if not s.get(k):
                errs.append(f"source {sid}: missing {k}")
        if s.get("date") and not valid_date(s["date"]):
            errs.append(f"source {sid}: date must be a real calendar date written YYYY-MM-DD")
        if s.get("location", "").startswith("http") and not s.get("verified"):
            errs.append(f"source {sid}: URLs must carry \"verified\": true after the page was opened and matched the claim")
    if not b["findings"]:
        errs.append("at least one finding required")
    for i, f in enumerate(b["findings"], 1):
        if not f.get("claim"):
            errs.append(f"finding {i}: missing claim")
        if f.get("confidence") not in CONF:
            errs.append(f"finding {i}: confidence must be one of {CONF}")
        cited = f.get("sources", [])
        if not cited:
            errs.append(f"finding {i}: every claim needs at least one source")
        for c in cited:
            if c not in ids:
                errs.append(f"finding {i}: cites unknown source {c}")
    if len(b["findings"]) > 12:
        errs.append("more than 12 findings: this is a report, not a brief; split it")
    return errs


def to_markdown(b: dict) -> str:
    out = [f"# {b['question']}", "", f"Audience: {b['audience']}  |  Date: {b['date']}  |  Prepared by: {b['author']}", ""]
    out += ["## Bottom line", "", b["recommendation"], "", "## Findings", ""]
    out += ["| # | Finding | Confidence | Sources |", "| --- | --- | --- | --- |"]
    for i, f in enumerate(b["findings"], 1):
        note = f" ({md_cell(f['note'])})" if f.get("note") else ""
        out.append(f"| {i} | {md_cell(f['claim'])}{note} | {md_cell(f['confidence'])} | {md_cell(', '.join(f['sources']))} |")
    out += ["", "## Open questions", ""] + [f"- {q}" for q in b["open_questions"]] or ["- None"]
    out += ["", "## Next steps", ""] + [f"1. {s}" for s in b["next_steps"]]
    out += ["", "## Sources", ""]
    for s in b["sources"]:
        out.append(f"- **{s['id']}** {s['title']} ({s['type']}, {s['date']}): `{s['location']}`")
    return "\n".join(out) + "\n"


def to_html(b: dict) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{i}</td><td>{e(f['claim'])}{(' <span class=note>(' + e(f['note']) + ')</span>') if f.get('note') else ''}</td>"
        f"<td class=c-{f['confidence']}>{f['confidence']}</td><td>{e(', '.join(f['sources']))}</td></tr>"
        for i, f in enumerate(b["findings"], 1))
    oq = "".join(f"<li>{e(q)}</li>" for q in b["open_questions"]) or "<li>None</li>"
    ns = "".join(f"<li>{e(s)}</li>" for s in b["next_steps"])
    src = "".join(f"<li><b>{e(s['id'])}</b> {e(s['title'])} <span class=note>({e(s['type'])}, {e(s['date'])})</span><br><code>{e(s['location'])}</code></li>" for s in b["sources"])
    css = ("body{max-width:860px;margin:40px auto;padding:0 24px;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:#141414;background:#FCFCFC;line-height:1.45}"
           "h1{font-size:30px;letter-spacing:-.3px}h2{font-size:20px;border-bottom:2px solid #2600FF;padding-bottom:6px;margin-top:32px}"
           ".meta,.note{color:#7D7D7D;font-size:14px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #E7E7E7;vertical-align:top}"
           "th{background:#F7F6F5;font-size:13px;text-transform:uppercase;letter-spacing:.4px}.c-high{color:#00A558}.c-medium{color:#141414}.c-low{color:#F53B3A}"
           "code{background:#F3F3F3;padding:1px 4px;border-radius:3px;font-size:13px}.bl{background:#F7F6F5;border-left:4px solid #2600FF;padding:12px 16px}")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><title>{e(b['question'])}</title><style>{css}</style></head><body>"
            f"<h1>{e(b['question'])}</h1><p class=meta>Audience: {e(b['audience'])} &nbsp;|&nbsp; Date: {e(b['date'])} &nbsp;|&nbsp; Prepared by: {e(b['author'])}</p>"
            f"<h2>Bottom line</h2><p class=bl>{e(b['recommendation'])}</p>"
            f"<h2>Findings</h2><table><thead><tr><th>#</th><th>Finding</th><th>Confidence</th><th>Sources</th></tr></thead><tbody>{rows}</tbody></table>"
            f"<h2>Open questions</h2><ul>{oq}</ul><h2>Next steps</h2><ol>{ns}</ol><h2>Sources</h2><ul>{src}</ul></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", type=Path)
    ap.add_argument("output", nargs="?", type=Path, help=".md or .html")
    ap.add_argument("--check", action="store_true", help="validate only (defaults to the example file)")
    a = ap.parse_args(argv)
    src = a.input or EXAMPLE
    try:
        brief = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{src}: cannot read brief JSON ({e})")
    errs = validate(brief)
    if errs:
        print("brief validation failed:\n  " + "\n  ".join(errs))
        return 1
    if a.check or a.output is None:
        print(f"{src}: valid ({len(brief['findings'])} findings, {len(brief['sources'])} sources)")
        return 0
    a.output.parent.mkdir(parents=True, exist_ok=True)
    text = to_html(brief) if a.output.suffix.lower() in (".html", ".htm") else to_markdown(brief)
    a.output.write_text(text, encoding="utf-8")
    print(f"wrote {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
