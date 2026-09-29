#!/usr/bin/env python3
"""Shared pieces of the fleet scanners (`vi_fleet_scan.py`, `m_fleet_scan.py`, `c_fleet_scan.py`).

Every scanner writes the same four artefacts for a tree - an inventory CSV, a summary JSON, and a migration
backlog in `templates/tracker-item.json` shape as JSON and CSV - and merges the backlog across rescans the same
way. That behaviour lives here once. Language-specific reading, classification, and scoring stay in each scanner.
Standard library only.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
SCHEMA = ROOT / "templates" / "tracker-item.json"
BACKLOG_COLUMNS = ["id", "type", "title", "severity", "status", "component", "requirements", "hazards",
                   "opened", "closed", "owner", "notes"]
COMPONENT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")  # tools/tracker_import.py accepts exactly this
PATH_RE = re.compile(r" path: (.+)$")


def severity_for(score: int) -> str:
    return "low" if score <= 20 else "medium" if score <= 50 else "high" if score <= 100 else "critical"


def check_prefix(prefix: str) -> None:
    if not re.fullmatch(r"[A-Z]{2,6}", prefix):
        raise SystemExit(f"--prefix must be 2-6 upper-case letters, got {prefix!r}")


def component_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")[:32].rstrip("-")
    return slug or "root"


def item_path(item: dict) -> str:
    m = PATH_RE.search(item.get("notes", ""))
    return m.group(1) if m else ""


def merge_backlog(new_items: list[dict], previous: list[dict], prefix: str) -> tuple[list[dict], dict]:
    """Carry tracker state across rescans. Identity is the unit's tree-relative path (kept at the end of `notes`):
    a unit seen before keeps its id, status, owner, opened, closed, requirements, and hazards and only its
    title/severity/notes are refreshed; a new unit gets the next unused id; a previous item whose unit dropped out
    of the top N (or was re-classified) is carried forward untouched so nothing closed or in review disappears."""
    prev_by_path = {item_path(it): it for it in previous if item_path(it)}
    used = {it["id"] for it in previous}
    next_n = max([int(m.group(1)) for it in previous for m in [re.match(rf"{prefix}-CAP-(\d{{3}})$", it["id"])] if m] or [0]) + 1
    merged, seen, stats = [], set(), {"kept": 0, "new": 0, "carried": 0}
    for it in new_items:
        path = item_path(it)
        old = prev_by_path.get(path)
        if old:
            merged.append({**old, "title": it["title"], "severity": it["severity"], "notes": it["notes"]})
            stats["kept"] += 1
        else:
            while next_n <= 999 and f"{prefix}-CAP-{next_n:03d}" in used:
                next_n += 1
            if next_n > 999:
                break
            merged.append({**it, "id": f"{prefix}-CAP-{next_n:03d}"})
            used.add(merged[-1]["id"])
            next_n += 1
            stats["new"] += 1
        seen.add(path)
    for it in previous:
        if item_path(it) not in seen:
            merged.append(it)
            stats["carried"] += 1
    merged.sort(key=lambda it: it["id"])
    return merged, stats


def load_previous_backlog(path: Path) -> list[dict]:
    """The existing backlog is tracker state edited by hand; a file that exists but cannot be read is an error to
    fix (or bypass with --fresh), never a first run."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"{path}: existing backlog could not be read ({type(e).__name__}: {str(e)[:120]}); "
                         f"fix the file, or pass --fresh to discard it")
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or any(not isinstance(it, dict) or "id" not in it for it in items):
        raise SystemExit(f"{path}: existing backlog is not a list of tracker items; fix the file, or pass --fresh to discard it")
    return items


def validate_backlog(items: list[dict]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    id_re = re.compile(schema["properties"]["id"]["pattern"])
    for it in items:
        missing = [k for k in schema["required"] if k not in it]
        if missing or not id_re.match(it["id"]) or len(it["title"]) > 120:
            raise SystemExit(f"backlog item {it.get('id')} does not match templates/tracker-item.json")
        for key in ("type", "severity", "status"):
            if it[key] not in schema["properties"][key]["enum"]:
                raise SystemExit(f"backlog item {it['id']}: {key}={it[key]!r} not allowed")


def csv_text(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def backlog_csv_rows(items: list[dict]) -> list[dict]:
    return [{**it, "requirements": " ".join(it["requirements"]), "hazards": " ".join(it["hazards"]), "closed": it["closed"] or ""} for it in items]


def rel(p: Path) -> Path:
    return p.relative_to(ROOT) if p.is_relative_to(ROOT) else p


def safe_name(tree: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tree.resolve().name).strip("-") or "tree"


def finish_backlog(items: list[dict], backlog_path: Path, prefix: str, notes: list[str], fresh: bool) -> list[dict]:
    """Merge with the backlog already on disk (unless --fresh), append the merge note, validate against the schema."""
    previous = [] if fresh else load_previous_backlog(backlog_path)
    if previous:
        items, stats = merge_backlog(items, previous, prefix)
        notes.append(f"backlog merged with the previous {backlog_path.name}: {stats['kept']} kept (id/status/owner preserved), "
                     f"{stats['new']} new, {stats['carried']} carried forward from the previous run; use --fresh to start over")
    validate_backlog(items)
    return items


def backlog_about(tool: str, name: str, backlog_path: Path, backlog_csv_path: Path, what: str) -> str:
    return (f"Migration backlog generated by {tool} from {name}: {what}; rescans with the "
            f"same --name keep ids and statuses (identity = the path at the end of notes). "
            f"Report with: python tools/tracker_report.py --file {rel(backlog_path)}. "
            f"Merge into a tracker with: python tools/tracker_import.py --from csv --in {rel(backlog_csv_path)} "
            f"--out outputs/{name}-tracker.json --merge <your tracker.json> --prefix <PREFIX>")


# --- graph helpers shared by the dependency maps --------------------------------------------------------------

CLASS_FILL = {"port": "#DDF4DD", "wrap": "#FFF1C2", "retain": "#F8D0D0", "unreadable": "#DDDDDD"}


def leaf_first_order(node_ids: list[str], edges: list[dict], skip_kinds: tuple[str, ...] = ("ambiguous",)) -> tuple[list[str], list[list[str]]]:
    """Kahn's algorithm over `from -> to` dependency edges: units with no unported dependencies first. Nodes left
    over sit in cycles; they are grouped by mutual reachability and appended after the ordered part."""
    deps: dict[str, set[str]] = defaultdict(set)
    ids = set(node_ids)
    for e in edges:
        if e["kind"] not in skip_kinds and e["from"] in ids and e["to"] in ids:
            deps[e["from"]].add(e["to"])
    done, order = set(), []
    remaining = set(node_ids)
    while remaining:
        ready = sorted(p for p in remaining if not (deps[p] - done))
        if not ready:
            break
        order += ready
        done |= set(ready)
        remaining -= set(ready)
    cycles: list[list[str]] = []
    if remaining:
        rest = sorted(remaining)
        reach: dict[str, set[str]] = {}
        for p in rest:
            stack, seen = [p], set()
            while stack:
                for y in deps[stack.pop()]:
                    if y in remaining and y not in seen:
                        seen.add(y)
                        stack.append(y)
            reach[p] = seen
        grouped: set[str] = set()
        for p in rest:
            if p in grouped:
                continue
            group = sorted({p} | {q for q in rest if p in reach[q] and q in reach[p]})
            grouped |= set(group)
            cycles.append(group)
        order += rest
    return order, cycles


def dot_text(graph_name: str, nodes: list[dict], edges: list[dict], edge_style: dict[str, str], cap: int) -> str:
    """Graphviz text for a dependency map. `nodes` carry id, label, classification, and rank (higher = kept first
    when the graph is capped at `cap` nodes); the JSON map stays complete, the drawing is for eyes."""
    if len(nodes) > cap:
        keep = {n["id"] for n in sorted(nodes, key=lambda n: (-n["rank"], n["id"]))[:cap]}
        head = f"// {len(nodes)} nodes; drawing the {cap} with the highest rank (callers + complexity). The JSON map is complete.\n"
    else:
        keep, head = {n["id"] for n in nodes}, ""
    out = [head + f"digraph {graph_name} {{", "  rankdir=LR; node [shape=box, style=filled, fontname=Helvetica, fontsize=10];"]
    for n in nodes:
        if n["id"] in keep:
            fill = CLASS_FILL.get(n.get("classification", ""), "#FFFFFF")
            out.append(f'  "{n["id"]}" [label="{n["label"]}", fillcolor="{fill}"];')
    for e in edges:
        if e["from"] in keep and e["to"] in keep:
            attrs = edge_style.get(e["kind"], "")
            out.append(f'  "{e["from"]}" -> "{e["to"]}"' + (f" [{attrs}]" if attrs else "") + ";")
    out.append("}")
    return "\n".join(out) + "\n"


def call_tree_lines(root: str, edges_from: dict, label_of, extras_of, depth: int = 4) -> list[str]:
    """Indented Markdown list of what `root` calls, breadth-limited to `depth`; repeated nodes are marked once."""
    lines: list[str] = []
    seen: set[str] = set()

    def walk(p: str, d: int) -> None:
        if p in seen:
            lines.append("  " * d + "- " + label_of(p) + " (seen above)")
            return
        seen.add(p)
        lines.append("  " * d + "- " + label_of(p))
        targets = sorted({e["to"] for e in edges_from.get(p, [])})
        if d >= depth:
            if targets:
                lines.append("  " * (d + 1) + f"- ... {len(targets)} more callee(s)")
            return
        for t in targets:
            walk(t, d + 1)
        for x in extras_of(p):
            lines.append("  " * (d + 1) + "- " + x)

    walk(root, 0)
    return lines
