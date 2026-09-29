#!/usr/bin/env python3
"""Inventory a whole tree of LabVIEW VIs and write a fleet inventory plus a prioritised migration backlog.

    python tools/vi_fleet_scan.py <tree>                      # outputs/<tree>-fleet-inventory.csv, -fleet-summary.json,
                                                              # -migration-backlog.json, -migration-backlog.csv
    python tools/vi_fleet_scan.py <tree> --name lab-a --top 30 --jobs 4
    python tools/vi_fleet_scan.py --check                     # scan example-system/ and compare with example-system/fleet/expected/

The scanner walks the tree in sorted order and records every `.vi`, `.lvproj`, `.lvlib`, `.lvclass`, and
TestStand `.seq`. When the optional `lvkit` reader is on PATH each `.vi` is read with `lvkit describe`
and `lvkit unresolved` (per file, so one corrupt VI costs one row, not the run) and the tree is indexed
once with `lvkit index` + `lvkit query` for the call graph. Without lvkit every VI is still listed, with
`reader = "lvkit absent"` and only file-name and project-file evidence. Numbers in the outputs are what
the tools returned; nothing is typed in.

Classification is one of `retain`, `wrap`, `port`, `unreadable`, decided in that order of precedence:
  unreadable  no block diagram could be read (corrupt file, password protected, no diagram, lvkit absent
              and no other evidence)
  retain      FPGA, Real-Time, hardware-timed DAQmx, timed loops, RT FIFOs, or a VI under an RT/FPGA
              target in a .lvproj: LabVIEW is the right home
  wrap        proprietary or LabVIEW-only driver surfaces (DAQmx, VISA, IVI, modular-instrument drivers,
              Call Library Function, .NET/ActiveX, TestStand API, shared variables): call it from Python
  port        everything else: sequencing, maths, string/array handling, limits, file I/O, reporting
The `reasons` column names the evidence (which SubVI, primitive, project target, or file name matched).

complexity = primitives + 2*structures + 3*subvis + 5*unresolved + 2*max_nesting + connector_terminals
priority   = 100 + 10*min(callers, 5) + 20 if a recording sits beside the VI + 10 if exported docs do - min(complexity, 60)
             (higher = start sooner: widely called, evidence in hand, small)
Backlog ids are `<PREFIX>-CAP-nnn` (templates/tracker-item.json); the tracker id pattern stops at 999, so the
backlog holds the top `--top` port/wrap candidates by priority and the CSV holds every VI. Re-running with the
same --name merges into the existing backlog: a VI keeps its id, status, owner, and dates; new VIs get new ids;
items whose VI left the top N are carried forward (--fresh discards the old backlog).
Standard library only; exit 0 unless the tree is missing or `--check` fails.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
FIXTURE = ROOT / "example-system"
EXPECTED = FIXTURE / "fleet" / "expected"
SCHEMA = ROOT / "templates" / "tracker-item.json"
LVKIT_TIMEOUT_S = 300
ABSENT = "lvkit absent"

COLUMNS = [
    "path", "name", "library", "size_bytes", "sha256", "reader", "lv_version", "lock_state",
    "connector_signature", "inputs", "outputs", "subvi_count", "subvis", "primitive_count",
    "unresolved_count", "unresolved", "structure_count", "structures", "max_nesting",
    "callers_count", "impact_score", "health", "lvproj", "target", "sequences",
    "classification", "reasons", "complexity", "priority", "missing_inputs",
]
BACKLOG_COLUMNS = ["id", "type", "title", "severity", "status", "component", "requirements", "hazards",
                   "opened", "closed", "owner", "notes"]

# Evidence catalogue: (regex, reason). Matched case-insensitively against SubVI qualified names, primitive
# names, .lvproj target names/types, and the VI's own path. Retain outranks wrap.
RETAIN_SIGNALS = [
    (r"fpga", "FPGA"),
    (r"\bni[-_ ]?rio\b|\bnirio", "NI-RIO"),
    (r"real[- ]?time|\brt[ _-](main|fifo|target|loop)|\brt\b.*target|compactrio|crio|pxi rt", "Real-Time"),
    (r"timed (loop|sequence|structure)", "timed loop"),
    (r"daqmx (timing|configure clock|sample clock|trigger)|hardware[- ]timed|sample clock", "DAQmx hardware timing"),
    (r"scan engine", "Scan Engine"),
]
WRAP_SIGNALS = [
    (r"daqmx", "DAQmx"),
    (r"\bvisa\b", "VISA"),
    (r"\bivi\b|ivi[a-z]+", "IVI driver"),
    (r"\bni(scope|dmm|switch|fgen|hsdio|rfsa|rfsg|845x|can|sync|dcpower)\b", "modular-instrument driver"),
    (r"xnet", "NI-XNET"),
    (r"call library function", "Call Library Function (DLL)"),
    (r"\.net\b|dotnet|activex|automation open", ".NET/ActiveX"),
    (r"teststand", "TestStand API"),
    (r"shared variable|network stream|datasocket", "shared variable / network stream"),
    (r"modbus|opc ua|opc-ua", "fieldbus/OPC driver"),
]
STRUCTURE_KINDS = ("case", "while", "for", "sequence", "event", "disabled", "inplace", "timed")


# --- helpers ------------------------------------------------------------------------------------


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lvkit_path() -> str | None:
    return shutil.which("lvkit")


def run_lvkit(exe: str, args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=LVKIT_TIMEOUT_S, cwd=cwd)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {LVKIT_TIMEOUT_S}s"
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


def lvkit_version(exe: str) -> str:
    code, out, err = run_lvkit(exe, ["--version"])
    text = (out or err).strip().splitlines()
    return text[0] if code == 0 and text else "lvkit (version unknown)"


def error_line(stderr: str, stdout: str = "") -> str:
    lines = [ln.strip() for ln in (stderr + "\n" + stdout).splitlines() if ln.strip()]
    for ln in reversed(lines):
        if not ln.startswith(("File ", "Traceback", "^", "raise ", "return ")):
            return ln[:160]
    return (lines[-1] if lines else "lvkit failed")[:160]


def match_signals(texts: list[str], signals: list[tuple[str, str]]) -> list[str]:
    hits: list[str] = []
    for pattern, reason in signals:
        rx = re.compile(pattern, re.IGNORECASE)
        for t in texts:
            if rx.search(t):
                hits.append(f"{reason} ({t[:60]})")
                break
    return hits


# --- lvkit readers -------------------------------------------------------------------------------


def walk_body(nodes: list, depth: int, acc: dict) -> None:
    for n in nodes:
        if not isinstance(n, dict):
            continue
        kind = n.get("kind")
        if kind == "instance":
            q = str(n.get("qualified_name") or n.get("name") or "")
            if q.lower().endswith((".vi", ".vim")):
                acc["subvis"].add(q)
            else:
                acc["primitives"].append(q)
        elif kind == "scope":
            sk = str(n.get("scope_kind") or "other")
            acc["structures"][sk] = acc["structures"].get(sk, 0) + 1
            acc["max_nesting"] = max(acc["max_nesting"], depth + 1)
            for frame in n.get("frames") or []:
                if isinstance(frame, dict):
                    walk_body(frame.get("body") or [], depth + 1, acc)
            walk_body(n.get("body") or [], depth + 1, acc)


def describe(exe: str, path: Path) -> dict:
    code, out, err = run_lvkit(exe, ["describe", "--format", "json", "--no-auto-vilib", str(path)])
    if code != 0:
        return {"error": error_line(err, out)}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return {"error": f"describe returned non-JSON: {e}"}
    acc: dict = {"subvis": set(), "primitives": [], "structures": {}, "max_nesting": 0}
    walk_body(data.get("body") or [], 0, acc)
    inputs = [f"{t.get('name')}: {t.get('type')}" for t in data.get("inputs") or []]
    outputs = [f"{t.get('name')}: {t.get('type')}" for t in data.get("outputs") or []]
    props = data.get("properties") or {}
    health = data.get("health") or {}
    kind = props.get("kind") or {}
    return {
        "lv_version": str(props.get("lv_version") or ""),
        "lock_state": str(props.get("lock_state") or ""),
        "has_no_block_diagram": bool(kind.get("has_no_block_diagram", False)),
        "inputs": inputs,
        "outputs": outputs,
        "terminals": len(inputs) + len(outputs),
        "subvis": sorted(acc["subvis"]),
        "primitives": acc["primitives"],
        "structures": dict(sorted(acc["structures"].items())),
        "max_nesting": acc["max_nesting"],
        "health": sorted(k for k, v in health.items() if v is True and k != "is_broken"),
        "library": library_of(facts_subvis=acc["subvis"], class_context=data.get("class_context")),
    }


def library_of(facts_subvis: set, class_context) -> str:
    """Owning library/class when lvkit reports one; otherwise blank (a standalone VI)."""
    if isinstance(class_context, dict):
        for key in ("class", "library", "qualified_name", "name"):
            if class_context.get(key):
                return str(class_context[key])
    if isinstance(class_context, str):
        return class_context
    return ""


def unresolved(exe: str, path: Path) -> dict:
    code, out, err = run_lvkit(exe, ["unresolved", "--json", "--no-auto-vilib", str(path)])
    if code != 0:
        return {"error": error_line(err, out)}
    try:
        items = json.loads(out)
    except json.JSONDecodeError as e:
        return {"error": f"unresolved returned non-JSON: {e}"}
    found = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind", "unresolved")
        ident = it.get("identifier")
        name = it.get("name") or ident
        found.append(f"{kind}:{name}" + (f"({ident})" if ident and str(ident) != str(name) else ""))
    return {"unresolved": sorted(set(found))}


def index_tree(exe: str, tree: Path) -> tuple[dict[str, dict], str]:
    """Best-effort call graph for every VI in the tree. Returns ({abs path: {callers_count, impact_score}}, note)."""
    code, out, err = run_lvkit(exe, ["index", str(tree)], cwd=tree)
    if code != 0:
        return {}, "lvkit index failed (call-graph columns left blank): " + error_line(err, out)
    try:
        indexed = json.loads(out.strip().splitlines()[-1]).get("vis", "?") if out.strip() else "?"
    except (json.JSONDecodeError, AttributeError):
        indexed = "?"
    sql = "SELECT path, callers_count, impact_score FROM vi"
    code, out, err = run_lvkit(exe, ["query", "--no-refresh", "--format", "json", str(tree), sql], cwd=tree)
    if code != 0:
        return {}, "lvkit query failed (call-graph columns left blank): " + error_line(err, out)
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return {}, f"lvkit query returned non-JSON: {e}"
    rows: list[dict] = []
    if isinstance(data, dict) and "columns" in data:
        rows = [dict(zip(data["columns"], r)) for r in data.get("rows", []) if isinstance(r, list)]
    elif isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    graph: dict[str, dict] = {}
    for r in rows:
        raw = str(r.get("path") or "")
        if not raw:
            continue
        path = Path(raw) if Path(raw).is_absolute() else tree / raw
        graph[str(path.resolve())] = {"callers_count": r.get("callers_count"), "impact_score": r.get("impact_score")}
    return graph, f"lvkit index covered {indexed} VIs in the enclosing project (nearest .lvkit/ or .git root), call graph for {len(graph)}"


# --- project files and sequences -----------------------------------------------------------------


TARGET_TYPE_RE = re.compile(r"fpga|\brt\b|real[- ]?time|my computer|target|chassis|crio|pxi", re.IGNORECASE)


def is_target(item: ET.Element) -> bool:
    return item.get("Type", "") not in ("Dependencies", "Build", "VI", "Folder", "Library", "LVClass", "Document") \
        and bool(TARGET_TYPE_RE.search(item.get("Type", "")))


def read_lvproj(path: Path, tree: Path) -> dict:
    """Map every VI item in a .lvproj to its target chain. Targets nest (a cRIO chassis holds an FPGA Target), so a
    VI's `target` is every target on its path, outermost first: "RT Controller [RT CompactRIO] > Chassis [FPGA Target]"."""
    result = {"file": str(path.relative_to(tree).as_posix()), "targets": [], "vis": {}, "outside_tree": 0, "missing": 0, "error": ""}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return result

    def walk(item: ET.Element, chain: list[str]) -> None:
        for child in item.findall("Item"):
            c_type = child.get("Type", "")
            if c_type in ("Dependencies", "Build"):
                continue
            if c_type == "VI" and child.get("URL"):
                url = child.get("URL", "").replace("\\", "/")
                resolved = (path.parent / url).resolve()
                try:
                    resolved.relative_to(tree.resolve())
                except ValueError:
                    result["outside_tree"] += 1
                    continue
                if not resolved.is_file():
                    result["missing"] += 1
                    continue
                result["vis"].setdefault(str(resolved), {"lvproj": result["file"], "target": " > ".join(chain)})
                continue
            if is_target(child) or not chain:
                label = f"{child.get('Name', '')} [{c_type}]"
                result["targets"].append({"name": child.get("Name", ""), "type": c_type, "under": " > ".join(chain)})
                walk(child, chain + [label])
            else:
                walk(child, chain)

    walk(root, [])
    return result


def read_seq(path: Path, tree: Path) -> dict:
    head = path.read_bytes()[:4096]
    stripped = head.lstrip()
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        fmt = "xml"
    elif stripped.startswith(b"[") or stripped.startswith(b";"):
        fmt = "ini"
    else:
        fmt = "binary"
    refs: list[str] = []
    if fmt != "binary":
        text = path.read_text(encoding="utf-8", errors="replace")
        refs = sorted({m.group(1).strip().replace("\\", "/") for m in re.finditer(r"([^\"'<>\n=]+\.vi)(?=[\"'<\s]|$)", text, re.IGNORECASE | re.MULTILINE)})
    return {"file": str(path.relative_to(tree).as_posix()), "format": fmt, "vi_refs": refs,
            "note": "" if fmt != "binary" else "binary sequence file; save as XML (Sequence File Properties > File Format) or run SequenceFileConverter.exe -Format:XML, then rescan"}


# --- classification -------------------------------------------------------------------------------


def classify(row: dict, facts: dict, name_only: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if facts.get("error"):
        return "unreadable", [f"lvkit could not read the diagram: {facts['error']}"]
    if facts.get("lock_state") == "password_protected":
        return "unreadable", ["password protected: block diagram not readable"]
    if facts.get("has_no_block_diagram"):
        return "unreadable", ["no block diagram (control, global, or typedef)"]
    project_texts = [row["target"]] if row.get("target") else []
    diagram_texts = list(facts.get("subvis") or []) + list(facts.get("primitives") or [])
    name_texts = [row["path"]]
    retain = match_signals(project_texts, RETAIN_SIGNALS)
    retain += [f"{r} [SubVI/primitive]" for r in match_signals(diagram_texts, RETAIN_SIGNALS)]
    retain += [f"{r} [file name only]" for r in match_signals(name_texts, RETAIN_SIGNALS)]
    if retain:
        return "retain", retain
    wrap = [f"{r} [SubVI/primitive]" for r in match_signals(diagram_texts, WRAP_SIGNALS)]
    wrap += [f"{r} [file name only]" for r in match_signals(name_texts, WRAP_SIGNALS)]
    if wrap:
        return "wrap", wrap
    if name_only:
        return "unreadable", [ABSENT + ": diagram not read; file name and project file give no retain/wrap signal"]
    n_prim, n_sub, structs = len(facts.get("primitives") or []), len(facts.get("subvis") or []), facts.get("structures") or {}
    reasons.append(f"sequencing/maths: {n_prim} primitives, {n_sub} SubVIs, "
                   + (", ".join(f"{v} {k}" for k, v in structs.items()) or "no structures"))
    if facts.get("unresolved"):
        reasons.append(f"{len(facts['unresolved'])} unresolved primitive mapping(s) to settle by hand")
    if facts.get("unresolved_error"):
        reasons.append("unresolved-primitive count unknown (lvkit unresolved failed); complexity is a lower bound")
    if facts.get("health"):
        reasons.append("LabVIEW health flags: " + ", ".join(facts["health"]))
    return "port", reasons


def complexity(facts: dict) -> int:
    return (len(facts.get("primitives") or []) + 2 * sum((facts.get("structures") or {}).values())
            + 3 * len(facts.get("subvis") or []) + 5 * len(facts.get("unresolved") or [])
            + 2 * int(facts.get("max_nesting") or 0) + int(facts.get("terminals") or 0))


def priority(callers: int | None, missing: list[str], score: int) -> int:
    return 100 + 10 * min(callers or 0, 5) + (0 if "recording" in missing else 20) + (0 if "exported docs" in missing else 10) - min(score, 60)


INPUT_ONLY_RE = re.compile(r"[-_ .](samples?|inputs?|stimulus|stimuli|vectors?)$")


def is_recording(stem: str, filename: str) -> bool:
    """A recording is the rig's *output* saved beside the VI: <stem>*.csv/.tdms/.tsv whose name does not say it is
    the input side (<stem>_samples.csv feeds a replay; it proves nothing on its own)."""
    base, dot, ext = filename.rpartition(".")
    if not dot or ext not in ("csv", "tdms", "tsv") or not base.startswith(stem):
        return False
    return not INPUT_ONLY_RE.search(base)


def missing_inputs(vi: Path, classification: str, facts: dict | None = None) -> list[str]:
    stem = vi.stem.lower()
    siblings = {p.name.lower() for p in vi.parent.iterdir() if p.is_file()}
    missing = []
    if not any(is_recording(stem, s) for s in siblings):
        missing.append("recording")
    if not any(s.startswith(stem) and s.endswith((".html", ".htm")) for s in siblings):
        missing.append("exported docs")
    if classification == "unreadable":
        missing.append("readable diagram (export HTML or unlock)")
    if facts and facts.get("unresolved_error"):
        missing.append("unresolved-primitive count (re-run lvkit unresolved)")
    return missing


# --- scan -----------------------------------------------------------------------------------------


def discover(tree: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {"vi": [], "lvproj": [], "lvlib": [], "lvclass": [], "seq": []}
    for p in sorted(tree.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower().lstrip(".")
        if ext in found:
            found[ext].append(p)
    return found


def scan_vi(exe: str | None, vi: Path) -> dict:
    facts: dict = {}
    if exe:
        facts = describe(exe, vi)
        if not facts.get("error"):
            u = unresolved(exe, vi)
            if u.get("error"):
                facts["unresolved"] = None
                facts["unresolved_error"] = u["error"]
            else:
                facts["unresolved"] = u.get("unresolved", [])
    return facts


def sequences_by_vi(sequences: list[dict], vis: list[Path], tree: Path) -> dict[str, list[str]]:
    """Which sequence files call each VI (keyed by absolute VI path). A reference that carries a relative path is
    resolved against the sequence file's folder; a bare name (or an absolute path from another machine) matches by
    name, and is marked ambiguous when several VIs in the tree share that name."""
    by_name: dict[str, list[Path]] = {}
    for vi in vis:
        by_name.setdefault(vi.name.lower(), []).append(vi)
    by_path: dict[str, set[str]] = {}
    for s in sequences:
        seq_dir = (tree / s["file"]).parent
        for ref in s["vi_refs"]:
            if "/" in ref and not re.match(r"^([a-zA-Z]:)?/", ref):
                candidate = (seq_dir / ref).resolve()
                if candidate.is_file():
                    by_path.setdefault(str(candidate), set()).add(s["file"])
                    continue
            name = ref.rsplit("/", 1)[-1].lower()
            matches = by_name.get(name, [])
            for vi in matches:
                by_path.setdefault(str(vi.resolve()), set()).add(s["file"] + (" (name match, ambiguous)" if len(matches) > 1 else ""))
    return {k: sorted(v) for k, v in by_path.items()}


def scan_tree(tree: Path, jobs: int = 1, use_index: bool = True, limit: int | None = None) -> dict:
    tree = tree.resolve()
    exe = lvkit_path()
    reader = lvkit_version(exe) if exe else ABSENT
    found = discover(tree)
    vis = found["vi"][:limit] if limit else found["vi"]
    notes: list[str] = []
    if not exe:
        notes.append(ABSENT + ": VIs listed from the file system only; install lvkit (integrations/lvkit.md) for diagram facts")

    projects = [read_lvproj(p, tree) for p in found["lvproj"]]
    vi_targets: dict[str, dict] = {}
    for proj in projects:
        for k, v in proj["vis"].items():
            vi_targets.setdefault(k, v)
    sequences = [read_seq(p, tree) for p in found["seq"]]
    seq_by_vi = sequences_by_vi(sequences, found["vi"], tree)

    graph: dict[str, dict] = {}
    if exe and use_index and vis:
        graph, note = index_tree(exe, tree)
        notes.append(note)

    facts_by_vi: dict[Path, dict] = {}
    if exe and vis:
        if jobs > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
                for vi, facts in zip(vis, pool.map(lambda p: scan_vi(exe, p), vis)):
                    facts_by_vi[vi] = facts
        else:
            for vi in vis:
                facts_by_vi[vi] = scan_vi(exe, vi)

    rows: list[dict] = []
    for vi in vis:
        facts = facts_by_vi.get(vi, {})
        rel = vi.relative_to(tree).as_posix()
        proj = vi_targets.get(str(vi.resolve()), {})
        row = {c: "" for c in COLUMNS}
        row.update({
            "path": rel, "name": vi.name, "size_bytes": vi.stat().st_size, "sha256": sha256(vi),
            "reader": reader if not facts.get("error") else f"{reader}: error",
            "lvproj": proj.get("lvproj", ""), "target": proj.get("target", ""),
            "sequences": ";".join(seq_by_vi.get(str(vi.resolve()), [])),
        })
        if facts and not facts.get("error"):
            row.update({
                "library": facts["library"], "lv_version": facts["lv_version"], "lock_state": facts["lock_state"],
                "connector_signature": f"({', '.join(facts['inputs'])}) -> ({', '.join(facts['outputs'])})",
                "inputs": len(facts["inputs"]), "outputs": len(facts["outputs"]),
                "subvi_count": len(facts["subvis"]), "subvis": ";".join(facts["subvis"]),
                "primitive_count": len(facts["primitives"]),
                "unresolved_count": len(facts["unresolved"]) if facts.get("unresolved") is not None else "",
                "unresolved": ";".join(facts.get("unresolved") or []),
                "structure_count": sum(facts["structures"].values()),
                "structures": ";".join(f"{k}:{v}" for k, v in facts["structures"].items()),
                "max_nesting": facts["max_nesting"],
                "health": ";".join(facts["health"]) or "ok",
            })
            if facts.get("unresolved_error"):
                row["unresolved"] = "lvkit unresolved failed (count unknown): " + facts["unresolved_error"]
        g = graph.get(str(vi.resolve()), {})
        if g:
            row["callers_count"] = g.get("callers_count") if g.get("callers_count") is not None else ""
            row["impact_score"] = g.get("impact_score") if g.get("impact_score") is not None else ""
        classification, reasons = classify(row, facts, name_only=not exe)
        score = complexity(facts) if facts and not facts.get("error") else 0
        missing = missing_inputs(vi, classification, facts)
        callers = int(row["callers_count"]) if str(row["callers_count"]).isdigit() else None
        row.update({
            "classification": classification, "reasons": "; ".join(reasons), "complexity": score,
            "priority": priority(callers, missing, score), "missing_inputs": ";".join(missing),
        })
        rows.append(row)

    by_class = {k: sum(1 for r in rows if r["classification"] == k) for k in ("port", "wrap", "retain", "unreadable")}
    summary = {
        "tree": str(tree), "reader": reader, "notes": notes,
        "counts": {"vi": len(found["vi"]), "vi_scanned": len(vis), "lvproj": len(found["lvproj"]), "lvlib": len(found["lvlib"]),
                   "lvclass": len(found["lvclass"]), "seq": len(found["seq"])},
        "classification": by_class,
        "complexity_total": sum(int(r["complexity"]) for r in rows),
        "missing_recording": sum(1 for r in rows if "recording" in str(r["missing_inputs"])),
        "projects": [{"file": p["file"], "targets": p["targets"], "vis_in_tree": len(p["vis"]), "vis_outside_tree": p["outside_tree"], "vis_missing": p["missing"], "error": p["error"]} for p in projects],
        "sequences": sequences,
        "libraries": [p.relative_to(tree).as_posix() for p in found["lvlib"]],
        "classes": [p.relative_to(tree).as_posix() for p in found["lvclass"]],
    }
    return {"rows": rows, "summary": summary}


# --- backlog --------------------------------------------------------------------------------------


def severity_for(score: int) -> str:
    return "low" if score <= 20 else "medium" if score <= 50 else "high" if score <= 100 else "critical"


def build_backlog(rows: list[dict], top: int, prefix: str, opened: str) -> list[dict]:
    if not re.fullmatch(r"[A-Z]{2,6}", prefix):
        raise SystemExit(f"--prefix must be 2-6 upper-case letters, got {prefix!r}")
    candidates = [r for r in rows if r["classification"] in ("port", "wrap")]
    candidates.sort(key=lambda r: (-int(r["priority"]), r["classification"] != "port", r["path"]))
    items = []
    for n, r in enumerate(candidates[: min(top, 999)], start=1):
        component = component_slug(r["library"] or (r["path"].split("/")[0] if "/" in r["path"] else "root"))
        verb = "Port" if r["classification"] == "port" else "Wrap"
        title = f"{verb} {r['name']}"
        items.append({
            "id": f"{prefix}-CAP-{n:03d}", "type": "capability", "title": title[:120],
            "severity": severity_for(int(r["complexity"])), "status": "proposed", "component": component,
            "requirements": [], "hazards": [], "opened": opened, "closed": None, "owner": "test-automation",
            "notes": (f"{r['classification']}: {r['reasons']}. complexity {r['complexity']}, priority {r['priority']}, "
                      f"callers {r['callers_count'] or 'n/a'}. missing: {r['missing_inputs'] or 'none'}."
                      + (f" library: {r['library']}." if r["library"] else "") + f" path: {r['path']}"),
        })
    return items


COMPONENT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")  # tools/tracker_import.py accepts exactly this


def component_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")[:32].rstrip("-")
    return slug or "root"


PATH_RE = re.compile(r" path: (.+)$")


def item_path(item: dict) -> str:
    m = PATH_RE.search(item.get("notes", ""))
    return m.group(1) if m else ""


def merge_backlog(new_items: list[dict], previous: list[dict], prefix: str) -> tuple[list[dict], dict]:
    """Carry tracker state across rescans. Identity is the VI's tree-relative path (kept at the end of `notes`):
    a VI seen before keeps its id, status, owner, opened, closed, requirements, and hazards and only its
    title/severity/notes are refreshed; a new VI gets the next unused id; a previous item whose VI dropped out of
    the top N (or was re-classified) is carried forward untouched so nothing closed or in review disappears."""
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
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return [it for it in items or [] if isinstance(it, dict) and "id" in it]


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


def write_outputs(result: dict, out_dir: Path, name: str, top: int, prefix: str, opened: str, fresh: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": out_dir / f"{name}-fleet-inventory.csv",
        "summary": out_dir / f"{name}-fleet-summary.json",
        "backlog": out_dir / f"{name}-migration-backlog.json",
        "backlog_csv": out_dir / f"{name}-migration-backlog.csv",
    }
    items = build_backlog(result["rows"], top, prefix, opened)
    previous = [] if fresh else load_previous_backlog(paths["backlog"])
    notes = list(result["summary"]["notes"])
    if previous:
        items, stats = merge_backlog(items, previous, prefix)
        notes.append(f"backlog merged with the previous {paths['backlog'].name}: {stats['kept']} kept (id/status/owner preserved), "
                     f"{stats['new']} new, {stats['carried']} carried forward from the previous run; use --fresh to start over")
    validate_backlog(items)
    paths["inventory"].write_text(csv_text(result["rows"], COLUMNS), encoding="utf-8")
    summary = {**result["summary"], "notes": notes, "name": name, "backlog_items": len(items), "outputs": {k: str(v.relative_to(ROOT)) if v.is_relative_to(ROOT) else str(v) for k, v in paths.items()}}
    paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    rel = lambda p: p.relative_to(ROOT) if p.is_relative_to(ROOT) else p  # noqa: E731
    about = (f"Migration backlog generated by tools/vi_fleet_scan.py from {name}: top port/wrap candidates by priority; rescans with the "
             f"same --name keep ids and statuses (identity = the path at the end of notes). "
             f"Report with: python tools/tracker_report.py --file {rel(paths['backlog'])}. "
             f"Merge into a tracker with: python tools/tracker_import.py --from csv --in {rel(paths['backlog_csv'])} "
             f"--out outputs/{name}-tracker.json --merge <your tracker.json> --prefix <PREFIX>")
    paths["backlog"].write_text(json.dumps({"_about": about, "items": items}, indent=2) + "\n", encoding="utf-8")
    paths["backlog_csv"].write_text(csv_text(backlog_csv_rows(items), BACKLOG_COLUMNS), encoding="utf-8")
    return paths


def safe_name(tree: Path) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", tree.resolve().name).strip("-") or "tree"
    return base


def render_text(summary: dict, paths: dict[str, Path]) -> str:
    c, k = summary["counts"], summary["classification"]
    lines = [
        f"{summary['name']}: {c['vi_scanned']} of {c['vi']} VIs scanned, {c['lvproj']} .lvproj, {c['lvlib']} .lvlib, "
        f"{c['lvclass']} .lvclass, {c['seq']} .seq; reader: {summary['reader']}",
        f"classification: port {k['port']}, wrap {k['wrap']}, retain {k['retain']}, unreadable {k['unreadable']}; "
        f"complexity total {summary['complexity_total']}; {summary['missing_recording']} VIs without a recording beside them",
        f"backlog: {summary['backlog_items']} items -> {paths['backlog']}",
        f"inventory: {paths['inventory']}",
    ]
    lines += [f"note: {n}" for n in summary["notes"]]
    lines += [f"note: {s['file']}: {s['note']}" for s in summary["sequences"] if s["note"]]
    return "\n".join(lines)


# --- --check --------------------------------------------------------------------------------------


def expected_meta() -> dict:
    return json.loads((EXPECTED / "fleet.json").read_text(encoding="utf-8"))


def check(write: bool = False) -> int:
    """Scan example-system/ into a temp dir and compare with example-system/fleet/expected/ (regenerate with --write-expected)."""
    meta = expected_meta()
    exe = lvkit_path()
    reader = lvkit_version(exe) if exe else ABSENT
    variant = "nolvkit" if not exe else ("lvkit" if reader == meta["lvkit_reader"] else None)
    with tempfile.TemporaryDirectory() as tmp:
        result = scan_tree(FIXTURE, jobs=1, use_index=True)
        paths = write_outputs(result, Path(tmp), meta["name"], meta["top"], meta["prefix"], meta["opened"])
        actual_csv = paths["inventory"].read_text(encoding="utf-8")
        problems = []
        if result["summary"]["counts"] != meta["counts"]:
            problems.append(f"counts {result['summary']['counts']} != expected {meta['counts']}")
        if variant is None:
            print(f"fleet check: {reader} installed but expected outputs were derived with {meta['lvkit_reader']}; "
                  f"structure checked, text compare skipped")
        else:
            expected_csv = EXPECTED / f"fleet-inventory.{variant}.csv"
            if write:
                expected_csv.write_text(actual_csv, encoding="utf-8")
                print(f"wrote {expected_csv.relative_to(ROOT)}")
            elif not expected_csv.is_file():
                problems.append(f"missing {expected_csv.relative_to(ROOT)}; run --write-expected")
            elif expected_csv.read_text(encoding="utf-8") != actual_csv:
                problems.append(f"{expected_csv.relative_to(ROOT)} differs from a fresh scan ({reader})")
            if variant == "lvkit" and result["summary"]["classification"] != meta["classification_with_lvkit"]:
                problems.append(f"classification {result['summary']['classification']} != {meta['classification_with_lvkit']}")
        backlog = json.loads(paths["backlog"].read_text(encoding="utf-8"))["items"]
        validate_backlog(backlog)
        if problems:
            print("fleet check FAILED:\n  " + "\n  ".join(problems))
            return 1
        c = result["summary"]["counts"]
        print(f"fleet check ok: {c['vi']} VIs, {c['lvproj']} .lvproj, {c['seq']} .seq under example-system/ ({reader}); "
              f"{len(backlog)} backlog items validate against templates/tracker-item.json")
        return 0


# --- main -----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree", nargs="?", type=Path, help="directory holding .vi / .lvproj / .seq files")
    ap.add_argument("--name", help="output prefix (default: the tree's folder name)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--top", type=int, default=50, help="backlog size (max 999)")
    ap.add_argument("--prefix", default="VI", help="tracker id prefix, 2-6 upper-case letters")
    ap.add_argument("--opened", default=dt.date.today().isoformat(), help="date stamped on backlog items (YYYY-MM-DD)")
    ap.add_argument("--jobs", type=int, default=1, help="parallel lvkit processes (lvkit 0.8.4 can fail on a cold cache above 1)")
    ap.add_argument("--limit", type=int, help="scan only the first N VIs (smoke test on a huge tree)")
    ap.add_argument("--no-index", action="store_true", help="skip lvkit index/query (no callers/impact columns)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--fresh", action="store_true", help="ignore an existing <name>-migration-backlog.json instead of preserving its ids and statuses")
    ap.add_argument("--check", action="store_true", help="scan the fixture and compare with example-system/fleet/expected/")
    ap.add_argument("--write-expected", action="store_true", help="with --check: rewrite the expected CSV for this reader")
    a = ap.parse_args(argv)
    if a.check:
        return check(write=a.write_expected)
    if a.tree is None:
        ap.error("tree is required unless --check")
    if not a.tree.is_dir():
        print(f"not a directory: {a.tree}", file=sys.stderr)
        return 2
    result = scan_tree(a.tree, jobs=max(1, a.jobs), use_index=not a.no_index, limit=a.limit)
    paths = write_outputs(result, a.out_dir, a.name or safe_name(a.tree), a.top, a.prefix, a.opened, fresh=a.fresh)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    print(json.dumps(summary, indent=2) if a.json else render_text(summary, paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
