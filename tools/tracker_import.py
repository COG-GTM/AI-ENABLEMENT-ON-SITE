#!/usr/bin/env python3
"""Normalise a tracker export (Jira, GitLab, Azure DevOps JSON, or CSV) into the example-system/tracker.json schema.

    python tools/tracker_import.py --from jira   --in export.json    --out outputs/tracker-import.json
    python tools/tracker_import.py --from gitlab --in export.json    --out t.json --merge example-system/tracker.json
    python tools/tracker_import.py --from ado    --in workitems.json --out t.json
    python tools/tracker_import.py --from csv    --in export.csv     --out t.json
    python tools/tracker_report.py --file t.json                     # validate and report the result

Input shapes: jira = the /rest/api/2/search response ({"issues": [...]}) or a list of issues; gitlab = the
/api/v4/projects/{id}/issues list; ado = the /_apis/wit/workitems response ({"value": [...]}); csv = header
id,type,title,severity,status,component,requirements,hazards,opened,closed,owner,notes ('; '-separated lists).

Only the fields named below are read; everything else is dropped. Type, priority, and status values must be in
the allowlists or the import stops and prints the allowed set. Each item records its origin in "source"
("jira:SN-101"), which --merge uses as the key: re-importing updates that item in place instead of adding a copy,
so importing the same export twice yields identical output. New ids (SN-BUG-013) continue after the highest
existing id per kind. owner is a role, never a person: the CSV column, else --owner, else the existing value.
Validation is tools/tracker_report.load(); nothing here re-implements the schema.
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tracker_report  # noqa: E402

SCHEMA = json.loads(tracker_report.SCHEMA.read_text())
TYPES = SCHEMA["properties"]["type"]["enum"]
SEVERITIES = SCHEMA["properties"]["severity"]["enum"]
STATUSES = SCHEMA["properties"]["status"]["enum"]
FIELDS = SCHEMA["required"]
CSV_COLUMNS = set(FIELDS)
MODES = ("jira", "gitlab", "ado", "csv")
DEFAULT_OWNER = "unassigned"
DEFAULT_COMPONENT = "unassigned"

PREFIX_RE = re.compile(r"^[A-Z]{2,6}$")
REQ_RE = re.compile(SCHEMA["properties"]["requirements"]["items"]["pattern"])
HAZ_RE = re.compile(SCHEMA["properties"]["hazards"]["items"]["pattern"])
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
COMPONENT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
SOURCE_RE = re.compile(r"^(jira|gitlab|ado|csv):[A-Za-z0-9._/#-]{1,64}$")
EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
OWNER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_TITLE = SCHEMA["properties"]["title"]["maxLength"]
MAX_NOTES = 500
ADF_MAX_DEPTH = 20
ADF_CONTAINERS = {"doc", "bulletList", "orderedList", "listItem", "blockquote", "panel", "table", "tableRow", "expand"}

JIRA_TYPE = {"bug": "bug", "defect": "defect", "story": "capability", "task": "capability", "new feature": "capability",
             "improvement": "capability", "epic": "capability"}
JIRA_SEVERITY = {"highest": "critical", "blocker": "critical", "critical": "critical", "high": "high", "medium": "medium",
                 "major": "medium", "low": "low", "lowest": "low", "minor": "low", "trivial": "low"}
JIRA_STATUS = {"backlog": "proposed", "proposed": "proposed", "open": "open", "to do": "open", "reopened": "open",
               "in progress": "open", "selected for development": "open", "in review": "in_review", "code review": "in_review",
               "done": "closed", "closed": "closed", "resolved": "closed", "won't do": "wont_fix", "won't fix": "wont_fix"}
GITLAB_TYPE = {"bug": "bug", "defect": "defect", "incident": "defect", "capability": "capability", "feature": "capability",
               "enhancement": "capability"}
GITLAB_SEVERITY = {s: s for s in SEVERITIES}
GITLAB_STATE = {"opened": "open", "closed": "closed"}
GITLAB_WORKFLOW = {"proposed": "proposed", "in review": "in_review", "wont fix": "wont_fix"}
ADO_TYPE = {"bug": "bug", "issue": "defect", "impediment": "defect", "user story": "capability", "product backlog item": "capability",
            "feature": "capability", "epic": "capability", "task": "capability"}
ADO_SEVERITY = {"1": "critical", "2": "high", "3": "medium", "4": "low"}
ADO_STATUS = {"new": "proposed", "proposed": "proposed", "active": "open", "approved": "open", "committed": "open", "to do": "open",
              "doing": "open", "resolved": "in_review", "closed": "closed", "done": "closed", "removed": "wont_fix", "cut": "wont_fix"}


def fail(msg: str):
    raise SystemExit(f"tracker_import: {msg}")


def pick(table: dict, value, what: str, where: str) -> str:
    key = str(value).strip().lower() if value is not None else ""
    if key not in table:
        fail(f"{where}: unknown {what} {value!r}; allowed: {sorted(table)}")
    return table[key]


def text(value, where: str, what: str, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        fail(f"{where}: {what} must be a string")
    return value.strip()


def adf_text(node, where: str, depth: int = 0) -> str:
    """Plain text of a Jira Cloud (API v3) Atlassian Document Format description; one line per block."""
    if depth > ADF_MAX_DEPTH or not isinstance(node, dict) or not isinstance(node.get("type"), str):
        fail(f"{where}: description is not a string or a well-formed Atlassian document")
    if node["type"] == "text":
        return node.get("text", "") if isinstance(node.get("text"), str) else ""
    if node["type"] == "hardBreak":
        return "\n"
    content = node.get("content", [])
    if not isinstance(content, list):
        fail(f"{where}: description content must be a list")
    parts = [adf_text(c, where, depth + 1) for c in content]
    return "\n".join(p for p in parts if p) if node["type"] in ADF_CONTAINERS else "".join(parts)


def description(value, where: str, what: str) -> str:
    if isinstance(value, dict):
        return adf_text(value, where).strip()
    return text(value, where, what)


def named(obj: dict, key: str, where: str):
    v = obj.get(key)
    if v is None:
        return None
    if not isinstance(v, dict) or not isinstance(v.get("name"), str):
        fail(f"{where}: {key} must be an object with a name")
    return v["name"]


def date(value, where: str, what: str):
    if value in (None, ""):
        return None
    m = DATE_RE.match(str(value))
    if not m:
        fail(f"{where}: {what} must start with YYYY-MM-DD, got {value!r}")
    try:
        datetime.date.fromisoformat(m.group(1))
    except ValueError:
        fail(f"{where}: {what} is not a calendar date: {m.group(1)}")
    return m.group(1)


def kind_of(typ: str) -> str:
    return "CAP" if typ == "capability" else "BUG"


def component(value, where: str) -> str:
    c = (value or DEFAULT_COMPONENT).strip().lower().replace(" ", "-")
    if not COMPONENT_RE.match(c):
        fail(f"{where}: component {value!r} must match {COMPONENT_RE.pattern} after lowercasing")
    return c


def clip(value: str, limit: int, where: str, what: str) -> str:
    if len(value) > limit:
        print(f"note: {where}: {what} clipped to {limit} characters", file=sys.stderr)
        return value[:limit]
    return value


def make(source: str, where: str, *, title, typ, severity, status, comp, tags, opened, closed, notes, owner=None) -> dict:
    if not title:
        fail(f"{where}: title is required")
    if not opened:
        fail(f"{where}: opened date is required")
    tags = [t for t in tags if isinstance(t, str)]
    if owner is not None and not OWNER_RE.match(owner):
        fail(f"{where}: owner {owner!r} must be a role matching {OWNER_RE.pattern}")
    return {
        "type": typ, "title": clip(title, MAX_TITLE, where, "title"), "severity": severity, "status": status, "component": comp,
        "requirements": sorted({t for t in tags if REQ_RE.match(t)}), "hazards": sorted({t for t in tags if HAZ_RE.match(t)}),
        "opened": opened, "closed": closed, "owner": owner, "notes": clip(notes, MAX_NOTES, where, "notes"), "source": source,
    }


# ---- readers -------------------------------------------------------------------------------------

def links(value: str, pattern: re.Pattern, where: str, what: str) -> list:
    """CSV requirements/hazards are explicit links: every non-empty entry must match, unlike vendor labels."""
    out = [t.strip() for t in value.split(";") if t.strip()]
    bad = [t for t in out if not pattern.match(t)]
    if bad:
        fail(f"{where}: {what} {bad} must match {pattern.pattern}")
    return out


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        fail(f"cannot read {path}: {e}")


def as_list(data, key: str, where: str) -> list:
    items = data.get(key) if isinstance(data, dict) else data
    if not isinstance(items, list):
        fail(f"{where}: expected a list or an object with {key}[]")
    return items


def from_jira(path: Path):
    for n, it in enumerate(as_list(read_json(path), "issues", "jira input")):
        where = f"jira issue #{n}"
        if not isinstance(it, dict) or not isinstance(it.get("key"), str) or not isinstance(it.get("fields"), dict):
            fail(f"{where}: expected an object with key and fields")
        f, where = it["fields"], f"jira {it['key']}"
        if not EXTERNAL_ID_RE.match(it["key"]):
            fail(f"{where}: bad key")
        status = f.get("status") if isinstance(f.get("status"), dict) else {}
        comps = f.get("components") if isinstance(f.get("components"), list) else []
        yield make(f"jira:{it['key']}", where,
                   title=text(f.get("summary"), where, "summary", required=True),
                   typ=pick(JIRA_TYPE, named(f, "issuetype", where), "issuetype", where),
                   severity=pick(JIRA_SEVERITY, named(f, "priority", where), "priority", where),
                   status=pick(JIRA_STATUS, status.get("name"), "status", where),
                   comp=component(comps[0]["name"] if comps and isinstance(comps[0], dict) and isinstance(comps[0].get("name"), str) else None, where),
                   tags=f.get("labels") if isinstance(f.get("labels"), list) else [],
                   opened=date(f.get("created"), where, "created"), closed=date(f.get("resolutiondate"), where, "resolutiondate"),
                   notes=description(f.get("description"), where, "description"))


def from_gitlab(path: Path):
    for n, it in enumerate(as_list(read_json(path), "issues", "gitlab input")):
        where = f"gitlab issue #{n}"
        if not isinstance(it, dict) or not isinstance(it.get("iid"), int) or not isinstance(it.get("project_id"), int):
            fail(f"{where}: expected an object with integer iid and project_id")
        where = f"gitlab {it['project_id']}#{it['iid']}"
        labels = it.get("labels") if isinstance(it.get("labels"), list) else []
        scoped = dict(l.split("::", 1) for l in labels if isinstance(l, str) and "::" in l)
        state = pick(GITLAB_STATE, it.get("state"), "state", where)
        workflow = scoped.get("workflow")
        if workflow is not None:
            status = pick(GITLAB_WORKFLOW, workflow, "workflow label", where)
            if state == "closed" and status != "wont_fix":
                status = "closed"
        else:
            status = state
        yield make(f"gitlab:{it['project_id']}#{it['iid']}", where,
                   title=text(it.get("title"), where, "title", required=True),
                   typ=pick(GITLAB_TYPE, scoped.get("type", "incident" if it.get("issue_type") == "incident" else None), "type label", where),
                   severity=pick(GITLAB_SEVERITY, scoped.get("priority", scoped.get("severity")), "priority label", where),
                   status=status, comp=component(scoped.get("component"), where), tags=labels,
                   opened=date(it.get("created_at"), where, "created_at"), closed=date(it.get("closed_at"), where, "closed_at"),
                   notes=text(it.get("description"), where, "description"))


def from_ado(path: Path):
    for n, it in enumerate(as_list(read_json(path), "value", "ado input")):
        where = f"ado work item #{n}"
        if not isinstance(it, dict) or not isinstance(it.get("id"), int) or not isinstance(it.get("fields"), dict):
            fail(f"{where}: expected an object with integer id and fields")
        f, where = it["fields"], f"ado {it['id']}"
        area = text(f.get("System.AreaPath"), where, "System.AreaPath").split("\\")
        tags = [t.strip() for t in text(f.get("System.Tags"), where, "System.Tags").split(";")]
        yield make(f"ado:{it['id']}", where,
                   title=text(f.get("System.Title"), where, "System.Title", required=True),
                   typ=pick(ADO_TYPE, f.get("System.WorkItemType"), "System.WorkItemType", where),
                   severity=pick(ADO_SEVERITY, f.get("Microsoft.VSTS.Common.Priority"), "Microsoft.VSTS.Common.Priority", where),
                   status=pick(ADO_STATUS, f.get("System.State"), "System.State", where),
                   comp=component(area[-1] if len(area) > 1 else None, where), tags=tags,
                   opened=date(f.get("System.CreatedDate"), where, "System.CreatedDate"),
                   closed=date(f.get("Microsoft.VSTS.Common.ClosedDate"), where, "Microsoft.VSTS.Common.ClosedDate"),
                   notes=text(f.get("System.Description"), where, "System.Description"))


def from_csv(path: Path):
    try:
        reader = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
        rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        fail(f"cannot read {path}: {e}")
    fieldnames = reader.fieldnames or []
    if len(fieldnames) != len(CSV_COLUMNS) or set(fieldnames) != CSV_COLUMNS:
        fail(f"csv header must be exactly {sorted(CSV_COLUMNS)}, each once; got {fieldnames}")
    enums = {"type": dict(zip(TYPES, TYPES)), "severity": dict(zip(SEVERITIES, SEVERITIES)), "status": dict(zip(STATUSES, STATUSES))}
    for n, row in enumerate(rows, start=2):
        where = f"csv line {n}"
        if None in row or any(v is None for v in row.values()):
            fail(f"{where}: wrong number of columns")
        if not EXTERNAL_ID_RE.match(row["id"]):
            fail(f"{where}: id must match {EXTERNAL_ID_RE.pattern}")
        yield make(f"csv:{row['id']}", where, title=row["title"].strip(),
                   typ=pick(enums["type"], row["type"], "type", where), severity=pick(enums["severity"], row["severity"], "severity", where),
                   status=pick(enums["status"], row["status"], "status", where), comp=component(row["component"], where),
                   tags=links(row["requirements"], REQ_RE, where, "requirements") + links(row["hazards"], HAZ_RE, where, "hazards"),
                   opened=date(row["opened"], where, "opened"), closed=date(row["closed"], where, "closed"),
                   notes=row["notes"].strip(), owner=row["owner"].strip().lower() or None)


READERS = {"jira": from_jira, "gitlab": from_gitlab, "ado": from_ado, "csv": from_csv}


# ---- merge -------------------------------------------------------------------------------------

def merge(existing: list, imported: list, prefix: str, owner: str) -> tuple[list, int, int]:
    by_source = {}
    for it in existing:
        src = it.get("source")
        if src is not None:
            if not isinstance(src, str) or not SOURCE_RE.match(src):
                fail(f"{it.get('id')}: existing source {src!r} must match {SOURCE_RE.pattern}")
            if src in by_source:
                fail(f"existing items {by_source[src]['id']} and {it['id']} both carry source {src}; keep one before merging")
            by_source[src] = it
    counters = {"BUG": 0, "CAP": 0}
    for it in existing:
        kind, num = it["id"].rsplit("-", 2)[1:]
        counters[kind] = max(counters[kind], int(num))
    seen, updated, added = set(), 0, 0
    for new in imported:
        if new["source"] in seen:
            fail(f"duplicate external id {new['source']} in input")
        seen.add(new["source"])
        old = by_source.get(new["source"])
        kind = kind_of(new["type"])
        if old is None:
            counters[kind] += 1
            if counters[kind] > 999:
                fail(f"no free {prefix}-{kind}-nnn id left")
            old = {"id": f"{prefix}-{kind}-{counters[kind]:03d}", "owner": owner}
            existing.append(old)
            added += 1
        elif old["id"].rsplit("-", 2)[1] != kind:
            fail(f"{new['source']}: type changed to {new['type']} but {old['id']} is a {old['id'].rsplit('-', 2)[1]} id; "
                 "ids are never renamed - close the old item and re-file it under a new external id")
        else:
            updated += 1
        merged = {**old, **{k: v for k, v in new.items() if k != "owner"}, "owner": new["owner"] or old.get("owner") or owner}
        old.clear()
        old.update({k: merged[k] for k in FIELDS + ["source"] if k in merged})
    existing.sort(key=lambda i: i["id"])
    return existing, updated, added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="mode", choices=MODES, required=True)
    ap.add_argument("--in", dest="src", type=Path, required=True, help="export file (JSON, or CSV for --from csv)")
    ap.add_argument("--out", type=Path, required=True, help="tracker JSON to write; validated before it is kept")
    ap.add_argument("--merge", type=Path, help="existing tracker JSON to update (matched by source; never duplicated)")
    ap.add_argument("--prefix", default="SN", help="id prefix for new items (default SN)")
    ap.add_argument("--owner", default=DEFAULT_OWNER, help="owner role for new items without one (default unassigned)")
    a = ap.parse_args(argv)
    if not PREFIX_RE.match(a.prefix):
        fail(f"--prefix must match {PREFIX_RE.pattern}")
    if not OWNER_RE.match(a.owner):
        fail(f"--owner must match {OWNER_RE.pattern}")
    if a.merge is not None and a.merge.resolve() == a.out.resolve():
        fail("--out must differ from --merge; review the diff, then copy")
    existing, about = [], f"Tracker items imported with tools/tracker_import.py --from {a.mode}. Schema: templates/tracker-item.json."
    if a.merge is not None:
        doc = read_json(a.merge)
        existing = tracker_report.load(a.merge)
        about = doc.get("_about", about) if isinstance(doc, dict) else about
    imported = list(READERS[a.mode](a.src))
    items, updated, added = merge(existing, imported, a.prefix, a.owner)
    tmp = a.out.with_name(a.out.name + ".tmp")  # validate the candidate first; --out is only ever replaced whole
    tmp.write_text(json.dumps({"_about": about, "items": items}, indent=2) + "\n")
    try:
        tracker_report.load(tmp)
    except SystemExit as e:
        tmp.unlink()
        fail(f"result did not validate, {a.out} untouched:\n{e}")
    os.replace(tmp, a.out)
    print(f"{len(imported)} items read from {a.src}: {updated} updated, {added} added; {len(items)} items written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
