#!/usr/bin/env python3
"""Deterministic lexical inventory of a React tree and a leaf-first Angular migration backlog.

    python tools/react_fleet_scan.py example-system/web-app/react-prototype --name request-app
    python tools/react_fleet_scan.py --check

This scanner is static evidence, not a parser or transpiler. A service unit is emitted as `port` for
the shared prompt-pack/backlog contract; its reason names the intended Angular injectable or signal store.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from fleet_common import (BACKLOG_COLUMNS, OUT_DIR, ROOT, backlog_csv_rows, check_prefix, component_slug, csv_text,
                          finish_backlog, safe_name, severity_for)

TOOL = "tools/react_fleet_scan.py"
FIXTURE = ROOT / "example-system" / "web-app" / "react-prototype"
EXPECTED = FIXTURE / "expected"
EXTENSIONS = {".tsx", ".jsx", ".ts", ".js"}
SKIP_DIRS = {".git", "node_modules", "dist", ".angular", "coverage", "__pycache__"}
HOOK_RE = re.compile(r"\b(use[A-Z]\w*)\s*\(")
IMPORT_RE = re.compile(r"(?:import\s+(?:type\s+)?(?:[^'\";]*?\s+from\s+)?|export\s+[^'\";]*?\s+from\s+|import\s*\()\s*['\"]([^'\"]+)['\"]")
FUNCTION_COMPONENT_RE = re.compile(r"\bfunction\s+([A-Z]\w*)\s*\(")
ARROW_COMPONENT_RE = re.compile(r"\b(?:const|let|var)\s+([A-Z]\w*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$]\w*)\s*=>")
HOOK_DEFINITION_RE = re.compile(r"\bfunction\s+(use[A-Z]\w*)\s*\(|\b(?:const|let|var)\s+(use[A-Z]\w*)\s*=")
ROUTE_RE = re.compile(r"<Route\b[^>]*?\bpath\s*=\s*\{?\s*['\"]([^'\"]+)['\"]")
CONTEXT_RE = re.compile(r"\bcreateContext\s*(?:<[^;]*?>)?\s*\(")
TEST_SUFFIX_RE = re.compile(r"(?:\.test|\.spec)\.[^.]+$")
UI_PACKAGE_RE = re.compile(r"^(?:@mui/|@chakra-ui/|antd$|semantic-ui-|react-bootstrap$)")
BUILTIN_HOOKS = {"useState", "useEffect", "useContext", "useReducer", "useMemo", "useCallback", "useRef", "useLayoutEffect"}
CONCEPTS = [
    ("props", "input()"),
    ("callback props", "output()"),
    ("useState", "signal"),
    ("useEffect", "effect or lifecycle hook"),
    ("useMemo", "computed"),
    ("context", "injectable settings service"),
    ("custom hook", "injectable service or function"),
    ("react-router", "Angular Router"),
    ("controlled form", "reactive form"),
    ("list keys", "@for track"),
]
COLUMNS = ["path", "unit", "kind", "role", "classification", "source_classification", "angular_target", "create_context", "components", "hooks_defined",
           "hook_calls", "routes", "relative_imports", "external_packages", "test_references", "reasons"]


def rel(path: Path) -> str:
    return path.as_posix()


def source_paths(tree: Path) -> list[Path]:
    return sorted(p for p in tree.rglob("*")
                  if p.is_file() and p.suffix.lower() in EXTENSIONS and not SKIP_DIRS.intersection(p.parts))


def package_name(specifier: str) -> str:
    if specifier.startswith("@"):
        bits = specifier.split("/")
        return "/".join(bits[:2]) if len(bits) > 1 else specifier
    return specifier.split("/", 1)[0]


def resolve_import(source: Path, specifier: str, tree: Path) -> str | None:
    if not specifier.startswith("."):
        return None
    base = (source.parent / specifier).resolve()
    candidates = [base, *(base.with_suffix(ext) for ext in EXTENSIONS),
                  *(base / f"index{ext}" for ext in EXTENSIONS)]
    for candidate in candidates:
        if candidate.is_file() and candidate.is_relative_to(tree.resolve()):
            return candidate.relative_to(tree.resolve()).as_posix()
    return None


def read_unit(path: Path, tree: Path, tests: list[tuple[str, str]]) -> tuple[list[dict], list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    relpath = path.relative_to(tree).as_posix()
    components = sorted({m.group(1) for m in FUNCTION_COMPONENT_RE.finditer(text)
                         if re.search(r"<[A-Za-z][\w.-]*\b", text[m.end():])} |
                        {m.group(1) for m in ARROW_COMPONENT_RE.finditer(text)
                         if re.search(r"<[A-Za-z][\w.-]*\b", text[m.end():])})
    hooks_defined = sorted({a or b for m in HOOK_DEFINITION_RE.finditer(text) if (a := m.group(1)) or (b := m.group(2))})
    hook_calls = sorted(set(HOOK_RE.findall(text)))
    contexts = 1 if CONTEXT_RE.search(text) else 0
    routes = sorted(set(ROUTE_RE.findall(text)))
    imports = sorted(set(IMPORT_RE.findall(text)))
    relative = sorted({found for spec in imports if (found := resolve_import(path, spec, tree))})
    external = sorted({package_name(spec) for spec in imports if not spec.startswith(".")})
    if components:
        declarations = [(name, "component", "standalone component") for name in components]
    else:
        declarations = []
    declarations.extend((name, "custom-hook", "injectable service or function") for name in hooks_defined)
    if contexts:
        declarations.append((path.stem, "context", "injectable settings service"))
    if path.name.endswith(".config.ts") or path.name in ("vite.config.js", "vite.config.ts"):
        declarations = [(path.stem, "build-config", "retain build configuration")]
    if not declarations:
        declarations.append((path.stem, "service", "injectable service or signal store"))
    out = []
    ui_package = next((package for package in external if UI_PACKAGE_RE.match(package)), None)
    for name, kind, target in declarations:
        refs = sorted(test_path for test_path, body in tests if name in body or relpath in body)
        react_concepts = []
        if kind == "component":
            react_concepts.extend(("props", "callback props", "controlled form", "list keys"))
        if "useState" in hook_calls:
            react_concepts.append("useState")
        if "useEffect" in hook_calls:
            react_concepts.append("useEffect")
        if "useMemo" in hook_calls:
            react_concepts.append("useMemo")
        if kind == "context":
            react_concepts.append("context")
        if kind == "custom-hook":
            react_concepts.append("custom hook")
        if routes:
            react_concepts.append("react-router")
        role = "test" if TEST_SUFFIX_RE.search(relpath) else "implementation"
        source_classification = ("retain" if kind == "build-config" else
                                 "service" if kind in ("custom-hook", "context", "service") else "port")
        classification = "wrap" if ui_package else "port"
        if kind == "build-config":
            classification = "retain"
            target = "retain build configuration"
        if ui_package:
            target = "custom element or replace UI dependency"
        reasons = [f"{kind} identified lexically", f"Angular target: {target}"]
        if source_classification == "service":
            reasons.append("service maps to shared port class for prompt-pack compatibility")
        if refs:
            reasons.append("referenced by test file(s)")
        if external:
            reasons.append("external imports: " + ", ".join(external))
        unit_name = name if len(declarations) > 1 else relpath
        out.append({"path": relpath, "name": unit_name, "unit": f"{relpath}#{unit_name}",
                    "kind": kind, "role": role, "classification": classification,
                    "source_classification": source_classification, "angular_target": target,
                    "create_context": bool(contexts),
                    "components": components, "hooks_defined": hooks_defined,
                    "hook_calls": hook_calls, "routes": routes, "relative_imports": relative,
                    "external_packages": external, "test_references": refs, "react_concepts": sorted(set(react_concepts)),
                    "reasons": reasons, "package_specifiers": imports})
    edges = [{"from": relpath, "to": target, "kind": "relative-import", "via": spec}
             for spec in imports if (target := resolve_import(path, spec, tree))]
    return out, edges


def leaf_first(nodes: list[dict], edges: list[dict]) -> list[str]:
    paths = {n["path"] for n in nodes}
    deps: dict[str, set[str]] = {p: set() for p in paths}
    callers: dict[str, set[str]] = {p: set() for p in paths}
    for edge in edges:
        source, target = edge["from"], edge["to"]
        if source in paths and target in paths:
            deps[source].add(target)
            callers[target].add(source)
    ready = sorted(p for p in paths if not deps[p])
    order = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for caller in sorted(callers[current]):
            deps[caller].discard(current)
            if not deps[caller] and caller not in order and caller not in ready:
                ready.append(caller)
                ready.sort()
    order.extend(sorted(paths - set(order)))
    return order


def scan_tree(tree: Path) -> dict:
    tree = tree.resolve()
    files = source_paths(tree)
    tests = []
    for path in files:
        if TEST_SUFFIX_RE.search(path.name):
            try:
                tests.append((path.relative_to(tree).as_posix(), path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    nodes, edges = [], []
    for path in files:
        try:
            file_nodes, file_edges = read_unit(path, tree, tests)
        except OSError:
            relpath = path.relative_to(tree).as_posix()
            file_nodes = [{"path": relpath, "name": path.stem, "unit": relpath, "kind": "unreadable", "role": "implementation",
                           "classification": "unreadable", "angular_target": "unreadable", "components": [], "hooks_defined": [],
                           "hook_calls": [], "routes": [], "relative_imports": [], "external_packages": [],
                           "test_references": [], "react_concepts": [], "reasons": ["source file could not be read"],
                           "package_specifiers": []}]
            file_edges = []
        nodes.extend(file_nodes)
        edges.extend(file_edges)
    package_path = tree / "package.json"
    dependencies = {}
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            external = sorted(dependencies)
            nodes.append({"path": "package.json", "name": "package.json", "unit": "package.json", "kind": "build-config",
                          "role": "configuration", "classification": "retain", "angular_target": "retain build/package configuration",
                           "components": [], "hooks_defined": [], "hook_calls": [], "routes": [], "relative_imports": [],
                           "create_context": False,
                          "external_packages": external, "test_references": [], "react_concepts": [],
                          "reasons": ["retain package manifest and pin the Angular dependency graph"], "package_specifiers": external})
        except (OSError, json.JSONDecodeError):
            pass
    unit_paths = {n["path"] for n in nodes}
    edges = [e for e in edges if e["from"] in unit_paths and e["to"] in unit_paths]
    edges.sort(key=lambda e: (e["from"], e["to"], e["via"]))
    order = leaf_first(nodes, edges)
    for node in nodes:
        node["callers"] = sorted({e["from"] for e in edges if e["to"] == node["path"]})
        node["dependencies"] = sorted({e["to"] for e in edges if e["from"] == node["path"]})
    nodes.sort(key=lambda n: (n["path"], n["unit"]))
    counts = {"files": len(files), "units": len(nodes), "components": sum(n["kind"] == "component" for n in nodes),
              "custom_hooks": sum(n["kind"] == "custom-hook" for n in nodes), "relative_edges": len(edges),
              "test_references": sum(bool(n["test_references"]) for n in nodes)}
    classes = {key: sum(n["classification"] == key for n in nodes) for key in ("port", "service", "wrap", "retain", "unreadable")}
    classes["service"] = 0  # service concepts map to `port` for the shared pack contract
    return {"tree": str(tree), "scanner": TOOL, "language": "react", "framework": "react",
            "nodes": nodes, "edges": edges, "leaf_first_order": order,
            "concept_mappings": [{"react": r, "angular": a} for r, a in CONCEPTS],
            "counts": counts, "classification": classes, "external_dependencies": dependencies}


def backlog_title(filename: str, declarations: list[str], action: str) -> str:
    title = f"{action} {filename} ({', '.join(declarations)}) to Angular"
    if len(title) <= 120:
        return title
    fallback = ""
    for shown in range(len(declarations) - 1, -1, -1):
        remaining = len(declarations) - shown
        names = ", ".join(declarations[:shown])
        summary = f"{names}, +{remaining} more" if names else f"+{remaining} more"
        fallback = f"{action} {filename} ({summary}) to Angular"
        if len(fallback) <= 120:
            return fallback
    return fallback[:120].rstrip()


def artifacts(result: dict, out_dir: Path, name: str, prefix: str = "REA", opened: str = "2026-10-27",
              fresh: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{name}-react"
    rows = []
    for node in result["nodes"]:
        rows.append({k: (";".join(node[k]) if isinstance(node.get(k), list) else node.get(k, ""))
                     for k in COLUMNS})
    inventory = out_dir / f"{stem}-fleet-inventory.csv"
    inventory.write_text(csv_text(rows, COLUMNS), encoding="utf-8")
    dep = out_dir / f"{stem}-dependency-map.json"
    dep.write_text(json.dumps({k: result[k] for k in ("tree", "scanner", "language", "framework", "nodes", "edges",
                                                       "leaf_first_order", "concept_mappings", "external_dependencies")},
                              indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = out_dir / f"{stem}-fleet-summary.json"
    summary_data = {k: result[k] for k in ("tree", "language", "counts", "classification")}
    summary_data["outputs"] = {"inventory": inventory.name, "summary": summary.name, "dependency_map": dep.name,
                               "dot": f"{stem}-dependency-map.dot", "repo_map": f"{stem}-repo-map.md",
                               "concept_map": f"{stem}-concept-map.md", "backlog": f"{stem}-migration-backlog.json",
                               "backlog_csv": f"{stem}-migration-backlog.csv"}
    summary.write_text(json.dumps(summary_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dot = out_dir / f"{stem}-dependency-map.dot"
    lines = ["digraph react_migration {", "  rankdir=LR;"]
    for node in result["nodes"]:
        lines.append(f'  "{node["path"]}" [label="{node["name"]}\\n{node["kind"]}"];')
    for edge in result["edges"]:
        lines.append(f'  "{edge["from"]}" -> "{edge["to"]}" [label="{edge["via"]}"];')
    lines.append("}")
    dot.write_text("\n".join(lines) + "\n", encoding="utf-8")
    repo_map = out_dir / f"{stem}-repo-map.md"
    repo_map.write_text("# React repository map\n\n" + f"- Files: {result['counts']['files']}\n"
                        + f"- Units: {result['counts']['units']}\n- Relative import edges: {len(result['edges'])}\n\n"
                        + "## Leaf-first order\n\n" + "\n".join(f"{i}. `{p}`" for i, p in enumerate(result["leaf_first_order"], 1))
                        + "\n", encoding="utf-8")
    concept = out_dir / f"{stem}-concept-map.md"
    concept.write_text("# React to Angular concept map\n\n| React | Angular |\n| --- | --- |\n"
                       + "\n".join(f"| {m['react']} | {m['angular']} |" for m in result["concept_mappings"]) + "\n",
                       encoding="utf-8")
    backlog = out_dir / f"{stem}-migration-backlog.json"
    candidates: dict[str, list[dict]] = defaultdict(list)
    for node in result["nodes"]:
        if node["classification"] in ("port", "wrap") and node["role"] != "test":
            candidates[node["path"]].append(node)
    backlog_items = []
    for path in result["leaf_first_order"]:
        declarations = candidates.get(path)
        if not declarations:
            continue
        names = {
            name
            for node in declarations
            for name in (*node.get("components", []), *node.get("hooks_defined", []))
        }
        if any(node.get("create_context") for node in declarations):
            names.add(Path(path).stem)
        if not names:
            names.add(Path(path).stem)
        all_reasons = sorted({reason for node in declarations for reason in node["reasons"]})
        all_names = sorted(names)
        classification = "wrap" if any(node["classification"] == "wrap" for node in declarations) else "port"
        backlog_items.append({
            "id": f"{prefix}-CAP-{len(backlog_items) + 1:03d}",
            "type": "capability",
            "title": backlog_title(Path(path).name, all_names, "Wrap" if classification == "wrap" else "Port"),
            "severity": severity_for(50),
            "status": "proposed",
            "component": component_slug(path),
            "requirements": [],
            "hazards": [],
            "opened": opened,
            "closed": None,
            "owner": None,
            "notes": f"{'; '.join(all_reasons)}; declarations: {', '.join(all_names)}; path: {path}"
        })
    backlog_notes: list[str] = []
    backlog_items = finish_backlog(backlog_items, backlog, prefix, backlog_notes, fresh)
    about = f"Deterministic synthetic backlog from {TOOL}."
    if backlog_notes:
        about += " " + " ".join(backlog_notes)
    backlog.write_text(json.dumps({"_about": about, "items": backlog_items}, indent=2) + "\n", encoding="utf-8")
    backlog_csv = out_dir / f"{stem}-migration-backlog.csv"
    backlog_csv.write_text(csv_text(backlog_csv_rows(backlog_items), BACKLOG_COLUMNS), encoding="utf-8")
    return {"inventory": inventory, "summary": summary, "dependency_map": dep, "dot": dot, "repo_map": repo_map,
            "concept_map": concept, "backlog": backlog, "backlog_csv": backlog_csv}


def check(write: bool = False) -> int:
    result = scan_tree(FIXTURE)
    result["tree"] = "fixture"
    with tempfile.TemporaryDirectory() as temp:
        paths = artifacts(result, Path(temp), "request-app", fresh=True)
        compare = {key: (paths[key].name, paths[key].read_text(encoding="utf-8"))
                   for key in ("inventory", "summary", "dependency_map", "dot", "repo_map", "concept_map", "backlog", "backlog_csv")}
    if write:
        EXPECTED.mkdir(parents=True, exist_ok=True)
        for _, (name, body) in compare.items():
            (EXPECTED / name).write_text(body, encoding="utf-8")
        print(f"wrote React fleet expected outputs under {EXPECTED.relative_to(ROOT)}")
        return 0
    problems = [name for name, body in compare.values()
                if not (EXPECTED / name).is_file() or (EXPECTED / name).read_text(encoding="utf-8") != body]
    if problems:
        print("react-fleet check FAILED: " + ", ".join(problems) + "; run --check --write-expected")
        return 1
    print(f"react-fleet check ok: {result['counts']['files']} source files, {result['counts']['components']} components, "
          f"{len(result['edges'])} relative import edges, {len(result['leaf_first_order'])} leaf-first units")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tree", nargs="?", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--prefix", default="REA")
    parser.add_argument("--opened", default=dt.date.today().isoformat())
    parser.add_argument("--fresh", action="store_true", help="discard any existing backlog state and start new ids")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-expected", action="store_true")
    args = parser.parse_args(argv)
    check_prefix(args.prefix)
    if args.check:
        return check(args.write_expected)
    if not args.tree:
        parser.error("tree is required unless --check")
    result = scan_tree(args.tree)
    name = args.name or safe_name(args.tree)
    paths = artifacts(result, args.out_dir, name, args.prefix, args.opened, args.fresh)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    print(json.dumps(summary, indent=2) if args.json else
          f"React fleet: {result['counts']['files']} files, {result['counts']['components']} components; outputs in {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
