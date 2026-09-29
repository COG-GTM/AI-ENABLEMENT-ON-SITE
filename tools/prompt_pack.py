#!/usr/bin/env python3
"""Build one bounded context package ("prompt pack") per migration unit from a scanner's dependency map, so an agent
works on one unit with exactly the evidence it needs instead of reading the whole tree on every step.

    python tools/prompt_pack.py --map outputs/<name>-dependency-map.json [--out-dir outputs/packs/<name>] [--budget 8000]
                                [--all | --unit <path> ...] [--neighbor-lines 40] [--task-file my-task.md] [--json]

Input: the `*-dependency-map.json` written by tools/vi_fleet_scan.py, tools/m_fleet_scan.py, or tools/c_fleet_scan.py. The
sibling `*-fleet-inventory.csv` and `*-migration-backlog.json` (same prefix) are read when present: the inventory supplies
the per-unit reasons and missing inputs, the backlog supplies the tracker id and the default unit list (its port/wrap items).

Each pack is a Markdown file with fixed sections, in this order, and a manifest entry with its size:
  1. Unit            path, kind, classification + reasons, complexity, priority, callers, missing inputs (from the scan; no opinions)
  2. Task            what to do with this one unit and which skill's steps apply (per language; override with --task-file)
  3. Contract        where to write results and the `result.json` shape the pipeline's compare/report stages read
  4. Source          the unit's own text (MATLAB/C/C++); for a binary VI the node record plus the `lvkit describe` command to run
  5. Dependencies    each direct callee/include: path, classification, the names used (`via`), and a bounded excerpt
                     (a header or the first --neighbor-lines lines) so the agent sees the interface without opening the file
  6. Callers         who depends on this unit (paths only) - the blast radius, not more context
  7. Open questions  this unit's unresolved / dynamic / vendor / indirect entries from the map, verbatim
  8. Boundaries      what static discovery did not prove, and the rule "do not open files outside this pack unless listed"

Budget: --budget is in estimated tokens (bytes / 4, stated in the manifest). Section 5 shrinks first (fewer excerpt lines,
then names only), then section 4 keeps its head and tail with a marker; sections 1-3 and 6-8 are never cut. `truncated` in the
manifest says what was cut. The manifest also records the whole-tree size so the saving is a number, not a claim.

Deterministic: packs are ordered by the map's leaf-first order (dependencies before dependents), ids come from the backlog
when the unit is in it (else UNIT-nnn), and identical inputs produce identical bytes. Standard library only. Nothing here
calls an agent; tools/pipeline_run.py does that (or, by default, does not).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from fleet_common import ROOT, OUT_DIR, rel

TOOL = "tools/prompt_pack.py"
TOKEN_BYTES = 4  # rough: 1 token per 4 bytes of English/code; the manifest says so

TASKS = {
    "labview": (
        "Follow `.devin/skills/labview-to-python/SKILL.md` steps 2-4 for **this one VI only**: (a) write the behaviour note "
        "(inputs, outputs, timing, error path) from `lvkit describe` and the connector pane; (b) map every SubVI and built-in in "
        "section 5/7 to a target-language equivalent or mark it `wrap`/`retain` with the reason; (c) implement the unit in the "
        "target language the plan chose (Python unless the plan says otherwise); (d) prove it with `python tools/bench_compare.py` "
        "against the rig recording named under *missing inputs* - if the recording is missing, stop and report `blocked`."
    ),
    "matlab": (
        "Follow `.devin/skills/matlab-to-code/SKILL.md` for **this one unit only**: (a) write the numeric-semantics note "
        "(types, rounding, saturation, indexing, NaN handling) from the source in section 4; (b) list every callee in section 5 "
        "as `already ported` / `port first` / `toolbox - wrap` and stop if a `port first` callee has no proven twin yet; "
        "(c) implement the unit in the target language; (d) prove it with `python tools/bench_compare.py` against the vectors "
        "named under *missing inputs* - if there are no vectors, generate them from the MATLAB source *only if MATLAB/Octave is "
        "available and the owner agreed*, otherwise report `blocked: vectors`."
    ),
    "c": (
        "Follow `.devin/skills/bring-your-firmware/SKILL.md` step 3 and `.devin/skills/tdd/SKILL.md` for **this one unit only**: "
        "(a) confirm which of its includes/calls in section 5 are `retain`/`wrap` - those are the stub seam; (b) add the unit to the "
        "host build (`templates/host-harness/Makefile` style) with stubs from `hal_stub.h` for the seam functions; (c) write "
        "nominal / fault / boundary tests for the functions listed in section 1; (d) if a Python behavioural twin is wanted, write "
        "it and prove both with the same vectors (`/tdd --lang both`) - the twin is a reference model, not a translation. "
        "Retain units are not migration work: document the interface and stop."
    ),
}
SKILL_OF = {"labview": "/labview-to-python", "matlab": "/matlab-to-code", "c": "/bring-your-firmware then /tdd"}
TEXT_EXT = {".m", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


def detect_language(dep_map: dict) -> str:
    if "projects" in dep_map or "reader" in dep_map:
        return "labview"
    if "toolboxes" in dep_map:
        return "matlab"
    if "include_check" in dep_map or "target_only" in dep_map:
        return "c"
    raise SystemExit("cannot tell which scanner wrote this map (expected keys from vi_fleet_scan, m_fleet_scan, or c_fleet_scan)")


def sibling(map_path: Path, suffix: str) -> Path:
    name = map_path.name
    for tail in ("-dependency-map.json",):
        if name.endswith(tail):
            stem = name[: -len(tail)]
            break
    else:
        stem = map_path.stem
    return map_path.with_name(stem + suffix)


def load_inventory(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["path"]: r for r in csv.DictReader(fh)}


def load_backlog(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    out = {}
    for it in items:
        note = it.get("notes", "")
        if " path: " in note:
            out[note.rsplit(" path: ", 1)[1].strip()] = it
    return out


def excerpt(text: str, lines: int, language: str) -> str:
    rows = text.splitlines()
    if language == "matlab":
        # signature + leading help comment block
        keep = []
        for r in rows:
            if len(keep) >= lines:
                break
            keep.append(r)
            if keep and not r.strip().startswith(("%", "function")) and len(keep) > 1 and r.strip():
                break
        return "\n".join(keep)
    return "\n".join(rows[:lines]) + ("" if len(rows) <= lines else f"\n... ({len(rows) - lines} more lines)")


def fence(text: str, lang: str) -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def code_lang(path: str, language: str) -> str:
    if language == "matlab":
        return "matlab"
    return "cpp" if Path(path).suffix.lower() in (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx") else "c"


def head_tail(text: str, max_bytes: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= max_bytes:
        return text, False
    half = max(200, max_bytes // 2 - 60)
    b = text.encode("utf-8")
    head = b[:half].decode("utf-8", errors="ignore")
    tail = b[-half:].decode("utf-8", errors="ignore")
    return head + f"\n\n... [{len(b) - 2 * half} bytes cut to fit the budget; open the file if you need the middle] ...\n\n" + tail, True


class PackBuilder:
    def __init__(self, dep_map: dict, tree: Path, language: str, inventory: dict, backlog: dict, name: str, out_dir: Path,
                 budget: int, neighbor_lines: int, task_text: str | None):
        self.m, self.tree, self.language = dep_map, tree, language
        self.inv, self.backlog, self.name, self.out_dir = inventory, backlog, name, out_dir
        self.budget, self.neighbor_lines = budget, neighbor_lines
        self.task_text = task_text or TASKS[language]
        self.nodes = {n["path"]: n for n in dep_map["nodes"]}
        self.out_edges: dict[str, list[dict]] = {}
        self.in_edges: dict[str, list[dict]] = {}
        for e in dep_map["edges"]:
            self.out_edges.setdefault(e["from"], []).append(e)
            self.in_edges.setdefault(e["to"], []).append(e)
        self.text_cache: dict[str, str | None] = {}

    def read(self, path: str) -> str | None:
        if path not in self.text_cache:
            p = self.tree / path
            if p.is_file() and p.suffix.lower() in TEXT_EXT and p.stat().st_size < 2_000_000:
                try:
                    self.text_cache[path] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    self.text_cache[path] = None
            else:
                self.text_cache[path] = None
        return self.text_cache[path]

    def callers_of(self, path: str) -> list[str]:
        return sorted({e["from"] for e in self.in_edges.get(path, []) if e["kind"] not in ("project-member",)})

    def questions(self, path: str) -> list[str]:
        m, q = self.m, []
        for key, label in (("unresolved", "unresolved"), ("dynamic", "dynamic"), ("indirect_calls", "indirect / by-name"),
                           ("unresolved_includes", "unresolved include")):
            v = m.get(key, {})
            if isinstance(v, dict) and path in v:
                vals = v[path]
                if isinstance(vals, list):
                    q += [f"{label}: {x}" for x in vals]
                elif isinstance(vals, dict):
                    q += [f"{label}: {k} ({n})" for k, n in vals.items()]
                else:
                    q.append(f"{label}: {vals}")
        row = self.inv.get(path, {})
        for col in ("calls_vendor", "calls_toolbox", "unresolved_primitives", "external_subvis"):
            if row.get(col):
                q.append(f"{col}: {row[col]}")
        if self.language == "labview":
            ext = m.get("external", {})
            for lib, vis in ext.items() if isinstance(ext, dict) else []:
                for e in self.out_edges.get(path, []):
                    if e["kind"] == "external" and e["to"] in vis:
                        q.append(f"external SubVI: {e['to']} ({lib or 'no library'})")
        for e in self.out_edges.get(path, []):
            if e["kind"].startswith("ambiguous"):
                q.append(f"ambiguous edge: {e['via'] if isinstance(e['via'], str) else ', '.join(e['via'])} could be {e['to']}")
        return sorted(set(q))

    def build(self, path: str, pack_id: str, index: int, total: int) -> tuple[str, dict]:
        n = self.nodes[path]
        row = self.inv.get(path, {})
        item = self.backlog.get(path)
        callers = self.callers_of(path)
        deps = sorted((e for e in self.out_edges.get(path, []) if e["kind"] not in ("project-member",)), key=lambda e: (e["to"], e["kind"]))
        cls = n.get("classification", row.get("classification", "?"))
        s1 = [f"# Pack {pack_id}: `{path}`", "",
              f"Generated by `{TOOL}` from `{rel(self.map_path)}` (unit {index} of {total}, leaf-first order). Everything in sections 1, 5, 6, 7 "
              "is a static fact from the scan; the task in section 2 is the standing instruction for every unit of this language.", "",
              "## 1. Unit", "",
              f"- path: `{path}`", f"- kind: {n.get('kind', row.get('kind', 'VI' if self.language == 'labview' else '?'))}",
              f"- classification: **{cls}** - {row.get('reasons', 'see inventory')}",
              f"- complexity {n.get('complexity', row.get('complexity', '?'))}, priority {row.get('priority', '?')}, "
              f"callers {n.get('callers', n.get('callers_in_tree', len(callers)))}",
              f"- missing inputs: {row.get('missing_inputs') or 'none recorded'}",
              f"- tracker item: {item['id'] + ' (' + item['status'] + ')' if item else 'not in the backlog'}"]
        if n.get("functions"):
            s1.append("- functions defined: " + ", ".join(f"`{x}`" for x in n["functions"]))
        if n.get("library"):
            s1.append(f"- library: {n['library']}")
        if n.get("lvproj"):
            s1.append(f"- project: `{n['lvproj']}` target `{n.get('target', '')}`")
        if row.get("signature"):
            s1.append(f"- signature: `{row['signature']}`")
        if row.get("connector"):
            s1.append(f"- connector: `{row['connector']}`")
        s2 = ["", "## 2. Task", "", self.task_text, "",
              f"Skill: `{SKILL_OF[self.language]}`. Scope: this unit. Read section 5 before opening any other file."]
        results_dir = f"outputs/pipeline/{self.name}/results/{pack_id}/"
        s3 = ["", "## 3. Contract", "",
              f"- write everything you produce under `{results_dir}` (code, notes, vectors, comparison output)",
              f"- finish by writing `{results_dir}result.json`:", "",
              fence(json.dumps({"id": pack_id, "unit": path, "status": "done | blocked | failed", "target": "python | c | c# | retain | wrap",
                                "evidence": ["<relative path of each proof file, e.g. the bench_compare output>"],
                                "blocked_on": "<missing input or decision, when status is blocked>", "notes": "<one paragraph>"}, indent=2), "json"),
              "", "- `done` means the proof in `evidence` passed, not that code was written",
              "- do not edit files outside this pack's unit and its results folder; propose changes to shared files in `notes`"]
        text = self.read(path)
        s4 = ["", "## 4. Source", ""]
        src_body, src_cut = "", False
        if text is not None:
            src_body = text
            s4_header = f"`{path}` ({len(text.encode('utf-8'))} bytes):"
        elif self.language == "labview":
            s4_header = ("Binary VI: no text source. The node record from the dependency map is below; read the diagram with\n\n"
                         f"    lvkit describe --format json --no-auto-vilib \"{self.tree / path}\"\n"
                         f"    lvkit unresolved --json --no-auto-vilib \"{self.tree / path}\"\n")
            src_body = json.dumps(n, indent=2)
        else:
            s4_header = "no readable text source (binary, too large, or unreadable in the scan)"
        s6 = ["", "## 6. Callers (blast radius; do not open)", ""] + ([f"- `{c}`" for c in callers] or ["- none in the tree"])
        s7 = ["", "## 7. Open questions from the scan", ""] + ([f"- {q}" for q in self.questions(path)] or ["- none recorded for this unit"])
        s8 = ["", "## 8. Boundaries", "",
              "- the scan is static: it did not run, compile for the target, expand macros, or evaluate dynamic dispatch",
              "- edges are candidates by name; an `ambiguous` or `unresolved` entry is a question for the owner, not a guess to make",
              "- do not read files outside this pack unless section 5 names them; if you must, say so in `result.json` notes so the pack can be improved",
              f"- the whole tree is not the context: {len(self.nodes)} units exist, this pack is one", ""]
        fixed = "\n".join(s1 + s2 + s3 + s6 + s7 + s8)
        # dependencies with shrinking excerpts
        cut_notes = []
        for lines in (self.neighbor_lines, self.neighbor_lines // 2, 8, 0):
            s5 = ["", "## 5. Dependencies (direct)", ""]
            if not deps:
                s5.append("- none: a leaf unit")
            for e in deps:
                to = e["to"]
                tn = self.nodes.get(to, {})
                via = e["via"] if isinstance(e["via"], str) else ", ".join(e["via"])
                s5.append(f"- `{to}` [{e['kind']}] {tn.get('classification', 'outside the map')}" + (f", uses: `{via}`" if via else ""))
                dep_text = self.read(to) if lines else None
                if dep_text is not None:
                    s5.append("")
                    s5.append("  " + fence(excerpt(dep_text, lines, self.language), code_lang(to, self.language)).replace("\n", "\n  "))
                    s5.append("")
            body_src = fence(src_body, code_lang(path, self.language) if text is not None else "json") if src_body else ""
            s4_full = "\n".join(s4 + [s4_header, "", body_src])
            total_bytes = len((fixed + "\n".join(s5) + s4_full).encode("utf-8"))
            if total_bytes <= self.budget * TOKEN_BYTES or lines == 0:
                if lines != self.neighbor_lines:
                    cut_notes.append(f"dependency excerpts reduced to {lines} lines" if lines else "dependency excerpts removed (names only)")
                break
        remaining = self.budget * TOKEN_BYTES - len((fixed + "\n".join(s5)).encode("utf-8")) - len("\n".join(s4 + [s4_header, "", ""]).encode("utf-8")) - 20
        if src_body and len(body_src.encode("utf-8")) > remaining:
            body, cut = head_tail(src_body, max(400, remaining))
            body_src = fence(body, code_lang(path, self.language) if text is not None else "json")
            src_cut = cut
            if cut:
                cut_notes.append("source cut to head and tail")
        pack = "\n".join(s1 + s2 + s3 + s4 + [s4_header, "", body_src] + s5 + s6 + s7 + s8)
        data = pack.encode("utf-8")
        return pack, {"id": pack_id, "unit": path, "classification": cls, "kind": n.get("kind", ""), "bytes": len(data),
                      "tokens_est": math.ceil(len(data) / TOKEN_BYTES), "over_budget": len(data) > self.budget * TOKEN_BYTES,
                      "truncated": cut_notes, "source_included": text is not None, "source_cut": src_cut,
                      "dependencies": [e["to"] for e in deps], "callers": callers, "tracker_id": item["id"] if item else None}


def whole_tree_size(tree: Path, nodes: dict) -> dict:
    total = 0
    for p in nodes:
        f = tree / p
        if f.is_file():
            total += f.stat().st_size
    return {"files": len(nodes), "bytes": total, "tokens_est": math.ceil(total / TOKEN_BYTES)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True, type=Path, help="<name>-dependency-map.json from a fleet scanner")
    ap.add_argument("--tree", type=Path, help="override the tree path recorded in the map (e.g. after moving the outputs)")
    ap.add_argument("--out-dir", type=Path, help="default outputs/packs/<name>")
    ap.add_argument("--name", help="pipeline name used in the results path (default: derived from the map file name)")
    ap.add_argument("--budget", type=int, default=8000, help="per-pack budget in estimated tokens (bytes/4)")
    ap.add_argument("--neighbor-lines", type=int, default=40, help="excerpt length for each dependency")
    ap.add_argument("--all", action="store_true", help="one pack per node, not only backlog (port/wrap) units")
    ap.add_argument("--unit", action="append", default=[], help="pack only this unit path (repeatable)")
    ap.add_argument("--task-file", type=Path, help="Markdown replacing the default per-language task text")
    ap.add_argument("--json", action="store_true", help="print the manifest")
    a = ap.parse_args(argv)
    map_path = a.map if a.map.is_absolute() else (Path.cwd() / a.map)
    if not map_path.is_file():
        raise SystemExit(f"{a.map} not found")
    dep_map = json.loads(map_path.read_text(encoding="utf-8"))
    language = detect_language(dep_map)
    tree = (a.tree or Path(dep_map["tree"])).resolve()
    name = a.name or map_path.name.replace("-dependency-map.json", "")
    out_dir = a.out_dir or (OUT_DIR / "packs" / name)
    inventory = load_inventory(sibling(map_path, "-fleet-inventory.csv"))
    backlog = load_backlog(sibling(map_path, "-migration-backlog.json"))
    task_text = a.task_file.read_text(encoding="utf-8").strip() if a.task_file else None
    b = PackBuilder(dep_map, tree, language, inventory, backlog, name, out_dir, a.budget, a.neighbor_lines, task_text)
    b.map_path = map_path
    order = [p for p in dep_map.get("leaf_first_order", []) if p in b.nodes] + sorted(p for p in b.nodes if p not in set(dep_map.get("leaf_first_order", [])))
    if a.unit:
        missing = [u for u in a.unit if u not in b.nodes]
        if missing:
            raise SystemExit("not in the map: " + ", ".join(missing))
        units = [p for p in order if p in set(a.unit)]
    elif a.all:
        units = order
    else:
        units = [p for p in order if p in backlog]
        if not units:
            units = [p for p in order if b.nodes[p].get("classification") in ("port", "wrap")]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    entries, n_unit = [], 0
    for i, p in enumerate(units, 1):
        item = backlog.get(p)
        if item:
            pack_id = item["id"]
        else:
            n_unit += 1
            pack_id = f"UNIT-{n_unit:03d}"
        text, entry = b.build(p, pack_id, i, len(units))
        fname = f"{pack_id}.md"
        (out_dir / fname).write_text(text, encoding="utf-8")
        entry["file"] = str(rel(out_dir / fname))
        entries.append(entry)
    whole = whole_tree_size(tree, b.nodes)
    manifest = {
        "_about": f"Prompt packs written by {TOOL}: one bounded context package per migration unit. tokens_est = bytes / {TOKEN_BYTES} "
                  "(a rough estimate, not a tokenizer). Packs are ordered leaf-first; ids are tracker ids when the unit is in the backlog.",
        "map": str(rel(map_path)), "tree": str(tree), "language": language, "name": name, "budget_tokens": a.budget,
        "neighbor_lines": a.neighbor_lines, "task_source": str(a.task_file) if a.task_file else f"default ({language})",
        "packs": entries,
        "totals": {"packs": len(entries), "bytes": sum(e["bytes"] for e in entries), "tokens_est": sum(e["tokens_est"] for e in entries),
                   "max_pack_tokens_est": max((e["tokens_est"] for e in entries), default=0),
                   "over_budget": sum(1 for e in entries if e["over_budget"]), "truncated": sum(1 for e in entries if e["truncated"])},
        "whole_tree": whole,
        "comparison": (f"{len(entries)} agent runs x at most {max((e['tokens_est'] for e in entries), default=0)} tokens of context each, "
                       f"versus {whole['tokens_est']} tokens if the whole tree were sent on every step" if entries else "no units selected"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    index = [f"# Prompt packs: {name}", "", f"Source map `{rel(map_path)}`; {len(entries)} packs, budget {a.budget} tokens each (est.). {manifest['comparison']}.", "",
             "| # | id | unit | class | tokens (est.) | deps | cut |", "| --- | --- | --- | --- | --- | --- | --- |"]
    index += [f"| {i} | `{e['id']}` | `{e['unit']}` | {e['classification']} | {e['tokens_est']} | {len(e['dependencies'])} | {'; '.join(e['truncated']) or ''} |"
              for i, e in enumerate(entries, 1)]
    (out_dir / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(manifest, indent=2))
    else:
        t = manifest["totals"]
        print(f"{name} ({language}): {t['packs']} packs in {rel(out_dir)}; {t['tokens_est']} tokens est. total, max {t['max_pack_tokens_est']}, "
              f"{t['over_budget']} over budget, {t['truncated']} truncated; whole tree {whole['tokens_est']} tokens est.")
        print(f"index: {rel(out_dir / 'INDEX.md')}; manifest: {rel(out_dir / 'manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
