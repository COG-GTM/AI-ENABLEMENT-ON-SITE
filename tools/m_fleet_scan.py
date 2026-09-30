#!/usr/bin/env python3
"""Repository-scale MATLAB discovery: walk a tree of .m files, build the candidate call graph, classify each file
for migration, and write the inventory, dependency map, repo map, and tracker-shaped backlog. Standard library only,
no MATLAB required; deterministic (sorted traversal, stable ids).

    python tools/m_fleet_scan.py <tree> [--name N] [--top 50] [--prefix MAT] [--out-dir outputs] [--json]
    python tools/m_fleet_scan.py --check

What it reads, statically (this is a *lexical* scanner, not a MATLAB interpreter):
  kind         script | function | classdef | method (@Class folder) | package function (+pkg) | private function
  definitions  main function and local functions per file, class methods, property names
  calls        identifiers followed by `(` that are not local variables, bare names that match a tree function,
               `@name` handles, and `pkg.sub.fn` qualified names; comments, block comments, strings, and
               transposes are stripped first (see strip_code)
  resolution   local function > private/ of the same folder > tree function by name > core MATLAB > known toolbox
               > unresolved. Two tree functions with one name are reported as ambiguous, not picked.
  dynamic      eval/evalc/evalin/assignin/feval/str2func/run/cellfun-with-string are reported per file; a string
               *literal* argument that names a tree function becomes a `dynamic-literal` edge, anything else stays
               unresolved on purpose.

Classification (evidence in `reasons`):
  retain     Simulink API, instrument/DAQ I/O, MEX/Java/.NET bridges, or a graphics-only script
  wrap       depends on a named toolbox (Signal Processing, Optimization, ...) - keep in MATLAB behind a boundary or
             find a vetted library equivalent per function
  port       everything else; unresolved and dynamic calls raise complexity but do not change the class
  unreadable file could not be decoded or parsed at all

complexity = code_lines/10 + 2*structures + 3*out_edges + 5*(unresolved + dynamic) + 2*max_nesting + 3*toolbox_calls + local_functions
priority   = 100 + 10*min(callers, 5) + 20 if vectors sit beside the file + 10 if a test calls it - min(complexity, 60)

Outputs (outputs/<name>-m-*): inventory CSV (every file), summary JSON, dependency-map JSON + DOT (edges, unresolved,
dynamic, toolboxes, entry points, orphans, shadowing, cycles, leaf-first migration order), repo-map Markdown (the
deterministic facts an agent documents from), migration-backlog JSON + CSV (top --top port/wrap candidates,
templates/tracker-item.json shape; rescans keep ids and statuses). Tests and graphics scripts are inventoried, not
backlogged. None of this proves behaviour: /matlab-to-code exports golden vectors and bench_compare.py does that.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from fleet_common import (
    BACKLOG_COLUMNS, OUT_DIR, ROOT, backlog_about, backlog_csv_rows, call_tree_lines, check_prefix, component_slug, csv_text,
    dot_text, finish_backlog, leaf_first_order, rel, safe_name, severity_for,
)

FIXTURE = ROOT / "example-system" / "matlab-repo"
EXPECTED = FIXTURE / "expected"
TOOL = "tools/m_fleet_scan.py"

COLUMNS = [
    "path", "name", "kind", "role", "package", "class", "size_bytes", "sha256", "lines", "code_lines", "functions",
    "signature", "calls_tree", "calls_builtin", "calls_toolbox", "calls_unresolved", "dynamic_calls", "structures",
    "max_nesting", "callers_count", "workspace_inputs", "classification", "reasons", "complexity", "priority",
    "missing_inputs", "notes",
]

KEYWORDS = frozenset("""break case catch classdef continue else elseif end for function global if otherwise parfor
persistent return spmd switch try while methods properties events enumeration arguments import""".split())
OPENERS = frozenset("if for parfor while switch try function classdef methods properties events enumeration arguments spmd".split())
STRUCTURES = frozenset("if for parfor while switch try".split())

# Core MATLAB (no toolbox) names this scanner recognises. Frozen and deliberately incomplete: a name missing here
# shows up as `unresolved`, which is the honest outcome, not an error. Extend with --builtins <file> for a site list.
CORE_BUILTINS = frozenset("""
abs all any arrayfun assert bitand bitor bitshift bitxor builtin cat ceil cell cell2mat cellfun char circshift class
clc clear containers.Map cos cumsum datestr dec2hex deal diag diff disp double eps error exist exp eye false fclose
fgetl fieldnames fileparts find fix floor fopen fprintf fread fullfile func2str fwrite hex2dec idivide inputname int16
int32 int64 int8 interp1 intersect isa iscell ischar isempty isequal isfield isfile isfolder isKey ishandle isinteger
islogical isnan isnumeric isreal isrow isscalar isstruct isvector keys length license linspace load log log10 log2
logical lower max mean median mfilename min mod nargin nargout nnz norm not num2str numel onCleanup ones polyfit polyval
prod rand randn readmatrix readtable regexp regexprep rem repmat reshape rethrow round rmfield save setdiff setfield
sign sin size sort sprintf sqrt std strcat strcmp strcmpi strfind strjoin strrep strsplit strtrim struct sum tic toc
true typecast uint16 uint32 uint64 uint8 union unique upper validateattributes values warning writematrix writetable
xor zeros nan inf pi filter fft ifft conv deconv cumprod fliplr flipud trapz interp2 histc histcounts accumarray mat2str
str2double str2num int2str num2cell struct2cell cell2struct isspace isstring string strlength join split contains
startsWith endsWith erase replace lsqnonneg mldivide inv det rank pinv kron cross dot triu tril
functiontests localfunctions verifyTrue verifyFalse verifyEqual verifyEmpty runtests fix
addpath rmpath path cd pwd which exist genpath dir ls mkdir delete copyfile movefile tempdir tempname input keyboard pause
rng datetime duration seconds minutes hours days now clock cputime etime
""".split())

GRAPHICS = frozenset("""figure plot subplot stem stairs bar hist histogram xlabel ylabel zlabel title legend axis grid
hold surf mesh imagesc image colorbar drawnow gca gcf close uifigure uicontrol uitable app msgbox waitbar""".split())

TOOLBOX = {
    **{n: "Signal Processing Toolbox" for n in "fir1 fir2 firpm butter cheby1 cheby2 ellip freqz filtfilt decimate resample pwelch periodogram spectrogram hilbert xcorr findpeaks sosfilt designfilt".split()},
    **{n: "Optimization Toolbox" for n in "lsqcurvefit lsqnonlin fmincon fminunc linprog quadprog fsolve ga optimoptions".split()},
    **{n: "Statistics and Machine Learning Toolbox" for n in "fitlm fitglm normrnd normpdf normcdf kmeans pca regress ttest anova1 fitdist".split()},
    **{n: "Control System Toolbox" for n in "tf ss zpk step impulse bode lsim c2d d2c pid".split()},
    **{n: "Image Processing Toolbox" for n in "imshow imfilter imresize rgb2gray imbinarize regionprops bwlabel imread2".split()},
    **{n: "Curve Fitting Toolbox" for n in "fit cfit fittype".split()},
    **{n: "Parallel Computing Toolbox" for n in "parpool gcp batch parfeval".split()},
}

RETAIN_MARKERS = {
    **{n: "Simulink API" for n in "sim set_param get_param open_system load_system save_system simset add_block".split()},
    **{n: "instrument / DAQ I/O" for n in "daq daqlist serialport serial visadev visa tcpclient tcpip udpport instrfind fscanf instrreset".split()},
    **{n: "MEX / Java / .NET bridge" for n in "mex loadlibrary calllib javaObject javaMethod NET".split()},
}

DYNAMIC = frozenset("eval evalc evalin assignin feval str2func run".split())
DYNAMIC_STRING_FUNCS = frozenset("cellfun arrayfun structfun".split())
IDENT_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
FUNC_DEF_RE = re.compile(r"^\s*function\b\s*(?:(\[[^\]]*\]|[A-Za-z_]\w*)\s*=\s*)?([A-Za-z_]\w*)\s*(\(([^)]*)\))?")
CLASSDEF_RE = re.compile(r"^\s*classdef\b\s*(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")
ASSIGN_RE = re.compile(r"^\s*(\[[^\]]*\]|[A-Za-z_]\w*)(?:\s*(?:\([^()]*\)|\{[^{}]*\}|\.\w+))*\s*=(?!=)")
FOR_RE = re.compile(r"^\s*(?:for|parfor)\s+\(?\s*([A-Za-z_]\w*)\s*=")
DECL_RE = re.compile(r"^\s*(?:global|persistent)\s+(.+)$")
STRING_RE = re.compile(r"'((?:[^']|'')*)'|\"((?:[^\"]|\"\")*)\"")


# --- lexing ---------------------------------------------------------------------------------------------------


def strip_line(line: str, base: int = 0) -> tuple[str, list[str], bool]:
    """Return (code with strings/comments removed, string literals, continues) for one physical line.
    A quote starts a char array unless the previous non-blank char makes it a transpose (identifier, `)`, `]`, `}`,
    digit, `.`, or another quote)."""
    out, strings, i, n = [], [], 0, len(line)
    prev = " "
    while i < n:
        ch = line[i]
        if ch == "%":
            break
        if line.startswith("...", i):
            return "".join(out), strings, True
        if ch == '"' or (ch == "'" and not (prev.isalnum() or prev in "_)]}'.\"")):
            j = i + 1
            while j < n:
                if line[j] == ch:
                    if j + 1 < n and line[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            out.append(f" \x00{base + len(strings)} ")  # numbered placeholder keeps token boundaries and finds the literal again
            strings.append(line[i + 1:j].replace(ch * 2, ch))
            i = j + 1
            prev = "\x00"
            continue
        out.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1
    return "".join(out), strings, False


def strip_code(text: str) -> tuple[list[str], list[str]]:
    """Whole file -> (logical code lines, all string literals). Handles `%{ ... %}` block comments (which must stand
    alone on their lines) and `...` continuations."""
    code, strings, block, pending = [], [], 0, ""
    for raw in text.splitlines():
        s = raw.strip()
        if block:
            if s == "%}":
                block -= 1
            elif s == "%{":
                block += 1
            continue
        if s == "%{":
            block += 1
            continue
        line, strs, cont = strip_line(raw, len(strings))
        strings += strs
        pending += line + " "
        if cont:
            continue
        code.append(pending.rstrip())
        pending = ""
    if pending.strip():
        code.append(pending.rstrip())
    return code, strings


# --- per-file parse -------------------------------------------------------------------------------------------


def statement_tokens(line: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z_]\w*", line)]


def parse_file(path: Path, tree: Path) -> dict:
    relp = path.relative_to(tree).as_posix()
    data = path.read_bytes()
    notes = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        notes.append("non-UTF-8 bytes replaced")
    text = text.lstrip("\ufeff\ufffd")
    if "\r\n" in text:
        notes.append("CRLF line endings")
    code, strings = strip_code(text)
    parts = Path(relp).parts
    package = ".".join(p[1:] for p in parts[:-1] if p.startswith("+"))
    at_class = next((p[1:] for p in parts[:-1] if p.startswith("@")), "")
    in_private = len(parts) >= 2 and parts[-2] == "private"
    stem = path.stem

    funcs, variables, class_name, props = [], set(), "", set()
    for line in code:
        m = CLASSDEF_RE.match(line)
        if m and not class_name:
            class_name = m.group(1)
            continue
        m = FUNC_DEF_RE.match(line)
        if m:
            outs = re.findall(r"[A-Za-z_]\w*", m.group(1) or "")
            ins = re.findall(r"[A-Za-z_]\w*", m.group(4) or "")
            funcs.append({"name": m.group(2), "inputs": ins, "outputs": outs})
            variables.update(outs); variables.update(ins)
            continue
        m = ASSIGN_RE.match(line)
        if m:
            variables.update(re.findall(r"[A-Za-z_]\w*", m.group(1)))
        m = FOR_RE.match(line)
        if m:
            variables.add(m.group(1))
        m = DECL_RE.match(line)
        if m:
            variables.update(re.findall(r"[A-Za-z_]\w*", m.group(1)))
    variables |= {"obj", "varargout", "ans", "end", "nargin", "nargout"}

    # block structure: a stack of openers closed by a bare `end` statement. Structures count if/for/while/switch/try;
    # nesting is their maximum depth. Inside a classdef `methods` block, `out = name(args)` with no `function` keyword
    # declares a method defined in another file of the @folder, so `name` is local, not a call.
    structures, max_depth, stack, declared = 0, 0, [], set()
    for line in code:
        for stmt in re.split(r"[;,](?![^()\[\]]*[)\]])", line):
            st = stmt.strip()
            toks = statement_tokens(st)
            if not toks:
                continue
            head = toks[0]
            if st == "end":
                if stack:
                    stack.pop()
                continue
            if head in OPENERS:
                if head in STRUCTURES:
                    structures += 1
                    max_depth = max(max_depth, sum(1 for x in stack if x in STRUCTURES) + 1)
                stack.append(head)
                continue
            if stack and stack[-1] == "methods":
                m = re.match(r"^(?:\[[^\]]*\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z_]\w*)\s*\(", st)
                if m:
                    declared.add(m.group(1))
    nesting = max_depth
    first_code = next((l.strip() for l in code if l.strip()), "")
    is_script = not (first_code.startswith("function") or first_code.startswith("classdef"))

    if class_name:
        kind = "classdef"
        # property names are not calls
        in_props = False
        for line in code:
            s = line.strip()
            if s.startswith("properties"):
                in_props = True
                continue
            if s == "end":
                in_props = False
                continue
            if in_props:
                m = re.match(r"([A-Za-z_]\w*)", s)
                if m:
                    props.add(m.group(1))
    elif at_class:
        kind = "method"
    elif funcs and not is_script:
        kind = "private function" if in_private else "package function" if package else "function"
    else:
        kind = "script"
    variables |= props

    # call candidates
    joined = "\n".join(code)
    local_names = {f["name"] for f in funcs} | declared
    if class_name:
        local_names.add(class_name)
    candidates, handles, bare = defaultdict(int), set(), set()
    for m in IDENT_RE.finditer(joined):
        name = m.group(0)
        first = name.split(".")[0]
        if first in KEYWORDS or (first in variables and "." not in name):
            continue
        after = joined[m.end():m.end() + 1]
        before = joined[m.start() - 1] if m.start() else " "
        if before == "@":
            handles.add(name)
        elif after == "(":
            candidates[name] += 1
        elif not (first in variables and "." in name):
            bare.add(name)
    dynamic = []
    for name in list(candidates):
        base = name.split(".")[-1]
        if base in DYNAMIC or (base in DYNAMIC_STRING_FUNCS and name in candidates):
            for mm in re.finditer(r"\b" + re.escape(name) + r"\s*\(", joined):
                arg = joined[mm.end():mm.end() + 40].strip()
                lit = re.match(r"\x00(\d+)", arg)
                literal = None
                if lit:
                    ident = IDENT_RE.match(strings[int(lit.group(1))].strip())   # 'fn' or 'fn(args)'; anything else is not a name
                    literal = ident.group(0) if ident else None
                dynamic.append({"call": base, "literal": bool(lit), "name": literal})
            if base in DYNAMIC:
                del candidates[name]
    # names that appear as the string argument of a dynamic call (the only literals that can become an edge)
    literal_names = sorted({d["name"] for d in dynamic if d["name"]})

    main = funcs[0] if funcs and not is_script else None
    if main:
        sig = (("[" + ", ".join(main["outputs"]) + "] = " if len(main["outputs"]) > 1 else (main["outputs"][0] + " = " if main["outputs"] else ""))
               + main["name"] + "(" + ", ".join(main["inputs"]) + ")")
    else:
        sig = "script" if not class_name else f"classdef {class_name}"
    qualified = (package + "." if package else "") + (at_class + "." if at_class else "") + (class_name or stem)
    return {
        "path": relp, "name": stem, "qualified": qualified, "kind": kind, "package": package, "class": class_name or at_class,
        "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16], "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "code_lines": sum(1 for l in code if l.strip()), "funcs": funcs, "signature": sig, "candidates": dict(candidates),
        "handles": sorted(handles), "bare": sorted(bare), "dynamic": dynamic, "literal_names": literal_names,
        "structures": structures, "max_nesting": nesting, "variables": variables, "local_names": local_names,
        "notes": notes, "in_private": in_private, "folder": Path(relp).parent.as_posix(),
        "role": "test" if (parts[0] == "tests" or stem.lower().startswith("test")) else "source",
    }


# --- tree resolution ------------------------------------------------------------------------------------------


def discover(tree: Path) -> list[Path]:
    return sorted(p for p in tree.rglob("*.m") if p.is_file() and not any(part in (".git", "expected") for part in p.relative_to(tree).parts))


def resolve(files: list[dict], builtins: frozenset[str]) -> dict:
    by_name = defaultdict(list)       # unqualified function/script/class name -> files
    by_qualified = {}                 # pkg.fn / @Class -> file
    method_names = defaultdict(list)  # method name -> class files
    for f in files:
        if f["kind"] == "method":
            method_names[f["name"]].append(f)
            by_qualified[f["qualified"]] = f
            continue
        if f["kind"] == "private function":
            continue
        by_qualified[f["qualified"]] = f
        if not f["package"]:
            by_name[f["name"]].append(f)
        if f["kind"] == "classdef":
            for fn in f["funcs"][1:] if f["funcs"] and f["funcs"][0]["name"] == f["name"] else f["funcs"]:
                method_names[fn["name"]].append(f)
    private_by_folder = defaultdict(dict)
    for f in files:
        if f["kind"] == "private function":
            private_by_folder[Path(f["folder"]).parent.as_posix()][f["name"]] = f

    edges, callers = [], defaultdict(set)

    def add_edge(src: dict, dst: dict, kind: str, via: str) -> None:
        if dst["path"] == src["path"]:
            return
        edges.append({"from": src["path"], "to": dst["path"], "kind": kind, "via": via})
        callers[dst["path"]].add(src["path"])

    for f in files:
        tree_calls, builtin_calls, toolbox_calls, unresolved, shadow = [], [], [], [], []
        names = dict(f["candidates"])
        for h in f["handles"]:
            names.setdefault(h, 0)
        for b in f["bare"]:
            if b in by_name and b not in f["local_names"] and b not in names:
                names[b] = 0  # command syntax or bare script call
        for lit in f["literal_names"]:
            if lit in by_name or lit in by_qualified:
                target = by_qualified.get(lit) or by_name[lit][0]
                add_edge(f, target, "dynamic-literal", lit)
                tree_calls.append(lit + " (dynamic-literal)")
        for name in sorted(names):
            base = name.split(".")[-1]
            first = name.split(".")[0]
            handle = name in f["handles"] and name not in f["candidates"]
            kind = "handle" if handle else "call"
            if base in f["local_names"] and "." not in name:
                continue
            if name in by_qualified and "." in name:
                add_edge(f, by_qualified[name], "package" if by_qualified[name]["package"] else kind, name)
                tree_calls.append(name)
                continue
            if "." in name:
                if first in by_name or first in by_qualified:
                    continue  # static-looking access on a known name; the qualified form is checked above
                if base in method_names and first in f["variables"]:
                    for cls in method_names[base]:
                        add_edge(f, cls, "method-name", name)
                    tree_calls.append(name + " (method by name)")
                    continue
                if first in f["variables"]:
                    continue  # struct field / property access on a local
                if name in builtins or first in builtins:
                    builtin_calls.append(name)
                    continue
                unresolved.append(name)
                continue
            priv = private_by_folder.get(f["folder"], {}).get(name)
            if priv:
                add_edge(f, priv, "private", name)
                tree_calls.append(name)
                continue
            if name in by_name:
                targets = by_name[name]
                if len(targets) > 1:
                    for t in targets:
                        add_edge(f, t, "ambiguous", name)
                    unresolved.append(f"{name} (ambiguous: {len(targets)} definitions)")
                else:
                    add_edge(f, targets[0], kind, name)
                    tree_calls.append(name)
                if name in builtins or name in GRAPHICS:
                    shadow.append(name)
                continue
            if name in RETAIN_MARKERS:
                toolbox_calls.append(f"{name} [{RETAIN_MARKERS[name]}]")
                continue
            if name in TOOLBOX:
                toolbox_calls.append(f"{name} [{TOOLBOX[name]}]")
                continue
            if name in builtins or name in GRAPHICS:
                builtin_calls.append(name)
                continue
            unresolved.append(name)
        f["calls_tree"], f["calls_builtin"], f["calls_toolbox"], f["calls_unresolved"], f["shadow_calls"] = (
            sorted(set(tree_calls)), sorted(set(builtin_calls)), sorted(set(toolbox_calls)), sorted(set(unresolved)), shadow)
        f["workspace_inputs"] = sorted(b for b in f["bare"] if f["kind"] == "script" and b not in by_name and b not in builtins
                                       and b not in GRAPHICS and b not in TOOLBOX and "." not in b) if f["kind"] == "script" else []
    shadowing = sorted((f["path"], f["name"]) for f in files if f["name"] in (builtins | GRAPHICS) and f["kind"] in ("function", "script"))
    for f in files:
        f["callers"] = sorted(callers.get(f["path"], set()))
        f["shadows_builtin"] = (f["path"], f["name"]) in shadowing
    edges.sort(key=lambda e: (e["from"], e["to"], e["kind"], e["via"]))
    return {"edges": edges, "shadowing": shadowing, "by_name": by_name}


# --- classification and scoring ---------------------------------------------------------------------------------


def classify(f: dict) -> tuple[str, list[str]]:
    reasons = []
    if not f["code_lines"]:
        return "unreadable", ["no code after stripping comments"]
    retain = sorted({t.split("[")[1].rstrip("]") for t in f["calls_toolbox"] if t.split(" [")[0] in RETAIN_MARKERS})
    toolbox = sorted({t.split("[")[1].rstrip("]") for t in f["calls_toolbox"] if t.split(" [")[0] in TOOLBOX})
    graphics = [c for c in f["calls_builtin"] if c in GRAPHICS]
    if retain:
        return "retain", ["uses " + ", ".join(retain)]
    if f["kind"] == "script" and graphics and not f["calls_tree"] and not [c for c in f["calls_builtin"] if c not in GRAPHICS and c not in ("sprintf", "numel", "ones", "size")]:
        return "retain", ["graphics-only script (" + ", ".join(graphics[:4]) + ")"]
    if toolbox:
        reasons.append("toolbox: " + ", ".join(toolbox))
        cls = "wrap"
    else:
        cls = "port"
    if f["dynamic"]:
        kinds = sorted({d["call"] for d in f["dynamic"]})
        lit = sum(1 for d in f["dynamic"] if d["literal"])
        reasons.append(f"dynamic call ({', '.join(kinds)}; {lit} of {len(f['dynamic'])} with a string literal)")
    if f["calls_unresolved"]:
        reasons.append(f"{len(f['calls_unresolved'])} unresolved name(s)")
    if f["shadow_calls"]:
        reasons.append("calls a tree function that shadows a built-in: " + ", ".join(sorted(set(f["shadow_calls"]))))
    if f["kind"] == "script" and f["workspace_inputs"]:
        reasons.append("script reads caller workspace: " + ", ".join(f["workspace_inputs"][:5]))
    if f["kind"] in ("function", "package function", "private function") and not f["callers"] and f["role"] != "test":
        reasons.append("no callers found in the tree")
    if f["kind"] in ("classdef", "method"):
        reasons.append("object-oriented (" + f["kind"] + ")")
    if f.get("shadows_builtin"):
        reasons.append(f"defines `{f['name']}`, which shadows a MATLAB built-in; path order decides which runs")
    if not reasons:
        reasons.append("pure function, every call resolved")
    return cls, reasons


def complexity(f: dict, out_edges: int) -> int:
    return (f["code_lines"] // 10 + 2 * f["structures"] + 3 * out_edges + 5 * (len(f["calls_unresolved"]) + len(f["dynamic"]))
            + 2 * f["max_nesting"] + 3 * len(f["calls_toolbox"]) + max(0, len(f["funcs"]) - 1))


def priority(callers: int, missing: list[str], score: int) -> int:
    return 100 + 10 * min(callers, 5) + (0 if "vectors" in missing else 20) + (0 if "test" in missing else 10) - min(score, 60)


def missing_inputs(f: dict, tree: Path, files_by_path: dict) -> list[str]:
    missing = []
    folder = tree / Path(f["path"]).parent
    if not any(folder.glob(f"{f['name']}*vectors*.csv")) and not any(folder.glob(f"{f['name']}*.mat")):
        missing.append("vectors")
    if f["role"] != "test" and not any(files_by_path[c]["role"] == "test" for c in f["callers"]):
        missing.append("test")
    return missing


# --- scan ------------------------------------------------------------------------------------------------------


def scan_tree(tree: Path, builtins: frozenset[str] = CORE_BUILTINS) -> dict:
    tree = tree.resolve()
    if not tree.is_dir():
        raise SystemExit(f"{tree} is not a directory")
    paths = discover(tree)
    files, unreadable = [], []
    for p in paths:
        try:
            files.append(parse_file(p, tree))
        except (OSError, RecursionError, ValueError) as e:  # keep going: one bad file must not stop a 5,000-file scan
            unreadable.append({"path": p.relative_to(tree).as_posix(), "error": f"{type(e).__name__}: {str(e)[:80]}"})
    graph = resolve(files, builtins)
    files_by_path = {f["path"]: f for f in files}
    out_edges = defaultdict(list)
    for e in graph["edges"]:
        out_edges[e["from"]].append(e)
    rows, toolboxes, builtins_used = [], defaultdict(set), defaultdict(int)
    for f in files:
        f["classification"], f["reasons"] = classify(f)
        score = complexity(f, len({e["to"] for e in out_edges[f["path"]]}))
        missing = missing_inputs(f, tree, files_by_path)
        for t in f["calls_toolbox"]:
            toolboxes[t.split("[")[1].rstrip("]")].add(f["path"])
        for b in f["calls_builtin"]:
            builtins_used[b] += 1
        rows.append({
            "path": f["path"], "name": f["name"], "kind": f["kind"], "role": f["role"], "package": f["package"], "class": f["class"],
            "size_bytes": f["size_bytes"], "sha256": f["sha256"], "lines": f["lines"], "code_lines": f["code_lines"],
            "functions": len(f["funcs"]), "signature": f["signature"], "calls_tree": ";".join(f["calls_tree"]),
            "calls_builtin": ";".join(f["calls_builtin"]), "calls_toolbox": ";".join(f["calls_toolbox"]),
            "calls_unresolved": ";".join(f["calls_unresolved"]), "dynamic_calls": ";".join(sorted({d["call"] for d in f["dynamic"]})),
            "structures": f["structures"], "max_nesting": f["max_nesting"], "callers_count": len(f["callers"]),
            "workspace_inputs": ";".join(f["workspace_inputs"]), "classification": f["classification"], "reasons": "; ".join(f["reasons"]),
            "complexity": score, "priority": priority(len(f["callers"]), missing, score), "missing_inputs": ";".join(missing),
            "notes": "; ".join(f["notes"]),
        })
    for u in unreadable:
        rows.append({**{c: "" for c in COLUMNS}, "path": u["path"], "name": Path(u["path"]).stem, "kind": "unreadable", "role": "source",
                     "classification": "unreadable", "reasons": u["error"], "complexity": 0, "priority": 0, "callers_count": 0, "notes": u["error"]})
    rows.sort(key=lambda r: r["path"])
    order, cycles = leaf_first_order(sorted(f["path"] for f in files), graph["edges"])
    entry = sorted(f["path"] for f in files if not f["callers"] and f["role"] != "test" and f["kind"] == "script")
    orphans = sorted(f["path"] for f in files if not f["callers"] and f["role"] != "test" and f["kind"] in ("function", "package function", "private function"))
    tests = sorted(f["path"] for f in files if f["role"] == "test")
    classification = {k: sum(1 for r in rows if r["classification"] == k) for k in ("port", "wrap", "retain", "unreadable")}
    dep_map = {
        "_about": f"Candidate call graph of the .m tree written by {TOOL}. Edges are static: `call` = name followed by `(`, "
                  "`handle` = @name, `package` = qualified +pkg call, `private` = private/ folder, `method-name` = obj.method matched "
                  "by method name only (receiver type unknown), `dynamic-literal` = eval/feval/str2func/run with a string literal "
                  "naming a tree file, `ambiguous` = two tree files share the name. Unresolved and dynamic calls are listed, not guessed.",
        "tree": str(tree), "nodes": [{"path": f["path"], "name": f["qualified"], "kind": f["kind"], "role": f["role"], "classification": f["classification"],
                                       "complexity": next(r["complexity"] for r in rows if r["path"] == f["path"]), "callers": len(f["callers"])} for f in files],
        "edges": graph["edges"],
        "unresolved": {f["path"]: f["calls_unresolved"] for f in files if f["calls_unresolved"]},
        "dynamic": {f["path"]: sorted({d["call"] + (" (string literal)" if d["literal"] else " (computed)") for d in f["dynamic"]}) for f in files if f["dynamic"]},
        "toolboxes": {k: sorted(v) for k, v in sorted(toolboxes.items())},
        "builtins_used": dict(sorted(builtins_used.items())),
        "shadowing": [{"path": p, "shadows": n} for p, n in graph["shadowing"]],
        "entry_points": entry, "orphans": orphans, "tests": tests, "cycles": cycles, "leaf_first_order": order,
        "unreadable": unreadable,
    }
    summary = {
        "tool": TOOL, "tree": str(tree),
        "counts": {"m_files": len(paths), "parsed": len(files), "unreadable": len(unreadable), "functions": sum(len(f["funcs"]) for f in files),
                   "scripts": sum(1 for f in files if f["kind"] == "script"), "classes": sum(1 for f in files if f["kind"] == "classdef"),
                   "packages": len({f["package"] for f in files if f["package"]}), "tests": len(tests),
                   "edges": len(graph["edges"]), "unresolved_names": sum(len(f["calls_unresolved"]) for f in files),
                   "dynamic_calls": sum(len(f["dynamic"]) for f in files), "toolboxes": len(toolboxes), "cycles": len(cycles)},
        "classification": classification, "complexity_total": sum(int(r["complexity"]) for r in rows),
        "entry_points": entry, "orphans": orphans, "toolboxes": sorted(toolboxes), "shadowing": [p for p, _ in graph["shadowing"]],
        "notes": [
            "static candidate graph: identifiers followed by `(` that are not local variables; MATLAB path order, run-time dispatch, "
            "and toolbox availability were not evaluated",
            f"core-MATLAB list has {len(builtins)} names; anything else not defined in the tree is `unresolved`",
        ],
    }
    if unreadable:
        summary["notes"].append(f"{len(unreadable)} file(s) could not be parsed; see the inventory")
    return {"rows": rows, "summary": summary, "dep_map": dep_map, "files": files, "out_edges": out_edges}


# --- outputs ---------------------------------------------------------------------------------------------------


def build_backlog(rows: list[dict], top: int, prefix: str, opened: str) -> list[dict]:
    check_prefix(prefix)
    candidates = [r for r in rows if r["classification"] in ("port", "wrap") and r["role"] != "test"]
    candidates.sort(key=lambda r: (-int(r["priority"]), r["classification"] != "port", r["path"]))
    items = []
    for n, r in enumerate(candidates[: min(top, 999)], start=1):
        component = component_slug(r["package"] or (r["path"].split("/")[0] if "/" in r["path"] else "root"))
        verb = "Port" if r["classification"] == "port" else "Wrap"
        items.append({
            "id": f"{prefix}-CAP-{n:03d}", "type": "capability", "title": f"{verb} {r['name']} ({r['kind']})"[:120],
            "severity": severity_for(int(r["complexity"])), "status": "proposed", "component": component,
            "requirements": [], "hazards": [], "opened": opened, "closed": None, "owner": "test-automation",
            "notes": (f"{r['classification']}: {r['reasons']}. complexity {r['complexity']}, priority {r['priority']}, "
                      f"callers {r['callers_count']}. missing: {r['missing_inputs'] or 'none'}. path: {r['path']}"),
        })
    return items


M_EDGE_STYLE = {"call": "", "handle": 'style=dashed label="@"', "package": "", "private": "style=dotted",
                "method-name": 'style=dashed label="method?"', "dynamic-literal": 'color="#2600FF" label="dynamic"',
                "ambiguous": 'color=red style=dashed label="ambiguous"'}


def m_dot(dep_map: dict, cap: int) -> str:
    nodes = [{"id": n["path"], "label": f"{n['name']}\\n{n['kind']}", "classification": n["classification"], "rank": n["callers"] + n["complexity"]}
             for n in dep_map["nodes"]]
    return dot_text("m_tree", nodes, dep_map["edges"], M_EDGE_STYLE, cap)


def repo_map_md(name: str, result: dict) -> str:
    s, m, files_by_path = result["summary"], result["dep_map"], {f["path"]: f for f in result["files"]}
    rows_by_path = {r["path"]: r for r in result["rows"]}
    c, k = s["counts"], s["classification"]
    L = [f"# Repo map: {name}", "",
         f"Generated by `{TOOL}` from `{s['tree']}`. Every statement below is a static fact about the text of the .m files; "
         "nothing was executed. The agent that documents this repository starts from this file and the per-unit prompt packs, "
         "not from the whole tree.", "",
         "## Shape", "",
         f"- {c['m_files']} .m files: {c['scripts']} scripts, {c['functions']} functions (including local functions), {c['classes']} classes, "
         f"{c['packages']} packages, {c['tests']} test files, {c['unreadable']} unreadable",
         f"- classification: port {k['port']}, wrap {k['wrap']}, retain {k['retain']}, unreadable {k['unreadable']}",
         f"- {c['edges']} resolved call edges, {c['unresolved_names']} unresolved names, {c['dynamic_calls']} dynamic calls, "
         f"{c['toolboxes']} toolbox(es), {c['cycles']} dependency cycle(s)", ""]
    L += ["## Entry points (scripts nobody calls) and their call trees", ""]
    if not m["entry_points"]:
        L.append("- none found (every script is called by another file, or the tree has no scripts)")
    def label_of(p: str) -> str:
        f = files_by_path[p]
        return f"{f['path']} [{f['kind']}, {f['classification']}]"

    def extras_of(p: str) -> list[str]:
        f = files_by_path[p]
        return [x for x in (f"toolbox: {', '.join(f['calls_toolbox'])}" if f["calls_toolbox"] else "",
                            f"unresolved: {', '.join(f['calls_unresolved'])}" if f["calls_unresolved"] else "",
                            f"dynamic: {', '.join(sorted({x['call'] for x in f['dynamic']}))}" if f["dynamic"] else "") if x]

    for p in m["entry_points"]:
        L += call_tree_lines(p, result["out_edges"], label_of, extras_of) + [""]
    L += ["## Leaf-first migration order", "",
          "Units with no unported dependencies come first; port in this order and each unit's callees already have a twin "
          "when its own vectors are replayed. Tests and retain items are listed for completeness.", ""]
    for i, p in enumerate(m["leaf_first_order"], 1):
        r = rows_by_path[p]
        L.append(f"{i}. `{p}` - {r['kind']}, {r['classification']}, complexity {r['complexity']}, callers {r['callers_count']}")
    if m["cycles"]:
        L += ["", "Cycles (port together, or break the cycle first):"] + [f"- {' <-> '.join(g)}" for g in m["cycles"]]
    L += ["", "## Packages and classes", ""]
    pk = sorted({f["package"] for f in result["files"] if f["package"]})
    L += [f"- package `+{p.replace('.', '/+')}`: " + ", ".join(f["name"] for f in result["files"] if f["package"] == p) for p in pk] or ["- no packages"]
    cl = [f for f in result["files"] if f["kind"] in ("classdef", "method")]
    L += [f"- class `{f['class']}`: {f['path']} ({f['kind']}; methods: {', '.join(fn['name'] for fn in f['funcs']) or 'declared elsewhere'})" for f in cl] or ["- no classes"]
    L += ["", "## Toolboxes and retain markers", ""]
    L += [f"- {tb}: " + ", ".join(ps) for tb, ps in m["toolboxes"].items()] or ["- none detected (against the scanner's frozen list)"]
    L += ["", "## Dynamic calls (cannot be resolved statically)", ""]
    L += [f"- `{p}`: " + ", ".join(v) for p, v in m["dynamic"].items()] or ["- none"]
    L += ["", "## Unresolved names", "", "Not defined in the tree, not in the core list, not in the toolbox list. Each one is a question for the owner: "
          "a toolbox function, a MEX file, a generated file, or a variable the scanner mistook for a call.", ""]
    L += [f"- `{p}`: " + ", ".join(v) for p, v in m["unresolved"].items()] or ["- none"]
    L += ["", "## Shadowing", ""]
    L += [f"- `{x['path']}` defines `{x['shadows']}`, which is also a MATLAB built-in; path order decides which one runs" for x in m["shadowing"]] or ["- none"]
    L += ["", "## Orphans (functions with no callers in the tree)", ""]
    L += [f"- `{p}`" for p in m["orphans"]] or ["- none"]
    if m["unreadable"]:
        L += ["", "## Unreadable", ""] + [f"- `{u['path']}`: {u['error']}" for u in m["unreadable"]]
    L += ["", "## What this map does not know", "",
          "- which of two same-named functions MATLAB picks at run time (path order, `addpath` calls, current folder)",
          "- the receiver type of `obj.method(...)`; method edges are by name only",
          "- anything behind `eval`, `feval`, `str2func`, `run` with a computed argument",
          "- whether a toolbox is licensed or installed; names were matched against a frozen list",
          "- numeric behaviour: export golden vectors with `/matlab-to-code` and replay them with `tools/bench_compare.py`", ""]
    return "\n".join(L)


def write_outputs(result: dict, out_dir: Path, name: str, top: int, prefix: str, opened: str, fresh: bool = False, dot_cap: int = 60) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": out_dir / f"{name}-m-fleet-inventory.csv",
        "summary": out_dir / f"{name}-m-fleet-summary.json",
        "dependency_map": out_dir / f"{name}-m-dependency-map.json",
        "dependency_dot": out_dir / f"{name}-m-dependency-map.dot",
        "repo_map": out_dir / f"{name}-m-repo-map.md",
        "backlog": out_dir / f"{name}-m-migration-backlog.json",
        "backlog_csv": out_dir / f"{name}-m-migration-backlog.csv",
    }
    items = build_backlog(result["rows"], top, prefix, opened)
    notes = list(result["summary"]["notes"])
    items = finish_backlog(items, paths["backlog"], prefix, notes, fresh)
    paths["inventory"].write_text(csv_text(result["rows"], COLUMNS), encoding="utf-8")
    summary = {**result["summary"], "notes": notes, "name": name, "backlog_items": len(items), "outputs": {k: str(rel(v)) for k, v in paths.items()}}
    paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    paths["dependency_map"].write_text(json.dumps(result["dep_map"], indent=2) + "\n", encoding="utf-8")
    paths["dependency_dot"].write_text(m_dot(result["dep_map"], dot_cap), encoding="utf-8")
    paths["repo_map"].write_text(repo_map_md(name, result), encoding="utf-8")
    about = backlog_about(TOOL, name, paths["backlog"], paths["backlog_csv"], "top port/wrap candidates by priority (tests and graphics scripts excluded)")
    paths["backlog"].write_text(json.dumps({"_about": about, "items": items}, indent=2) + "\n", encoding="utf-8")
    paths["backlog_csv"].write_text(csv_text(backlog_csv_rows(items), BACKLOG_COLUMNS), encoding="utf-8")
    return paths


def render_text(summary: dict, paths: dict[str, Path]) -> str:
    c, k = summary["counts"], summary["classification"]
    lines = [
        f"{summary['name']}: {c['m_files']} .m files ({c['scripts']} scripts, {c['functions']} functions, {c['classes']} classes, "
        f"{c['packages']} packages, {c['tests']} tests); {c['edges']} call edges, {c['unresolved_names']} unresolved, {c['dynamic_calls']} dynamic",
        f"classification: port {k['port']}, wrap {k['wrap']}, retain {k['retain']}, unreadable {k['unreadable']}; complexity total {summary['complexity_total']}",
        f"entry points: {', '.join(summary['entry_points']) or 'none'}; toolboxes: {', '.join(summary['toolboxes']) or 'none'}",
        f"backlog: {summary['backlog_items']} items -> {paths['backlog']}",
        f"repo map: {paths['repo_map']}; dependency map: {paths['dependency_map']}",
    ]
    lines += [f"note: {n}" for n in summary["notes"]]
    return "\n".join(lines)


# --- --check ---------------------------------------------------------------------------------------------------


def check(write: bool = False) -> int:
    meta_path = EXPECTED / "m-fleet.json"
    with tempfile.TemporaryDirectory() as tmp:
        result = scan_tree(FIXTURE)
        paths = write_outputs(result, Path(tmp), "matlab-repo", 50, "MAT", "2026-01-05")
        actual = {"counts": result["summary"]["counts"], "classification": result["summary"]["classification"],
                  "entry_points": result["summary"]["entry_points"], "orphans": result["summary"]["orphans"],
                  "toolboxes": result["summary"]["toolboxes"], "shadowing": result["summary"]["shadowing"],
                  "backlog_items": len(json.loads(paths["backlog"].read_text(encoding="utf-8"))["items"])}
        inventory = paths["inventory"].read_text(encoding="utf-8")
        if write:
            EXPECTED.mkdir(exist_ok=True)
            meta_path.write_text(json.dumps({"_about": f"Expected shape of `python {TOOL} --check` over example-system/matlab-repo/. "
                                             f"Regenerate with --check --write-expected after a deliberate change.", **actual}, indent=2) + "\n", encoding="utf-8")
            (EXPECTED / "m-fleet-inventory.csv").write_text(inventory, encoding="utf-8")
            print(f"wrote {rel(meta_path)} and {rel(EXPECTED / 'm-fleet-inventory.csv')}")
            return 0
        if not meta_path.is_file():
            print(f"m-fleet check FAILED: missing {rel(meta_path)}; run --check --write-expected")
            return 1
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        problems = [f"{k}: {actual[k]} != expected {meta.get(k)}" for k in actual if actual[k] != meta.get(k)]
        if (EXPECTED / "m-fleet-inventory.csv").read_text(encoding="utf-8") != inventory:
            problems.append("m-fleet-inventory.csv differs from a fresh scan")
        if problems:
            print("m-fleet check FAILED:\n  " + "\n  ".join(problems))
            return 1
        c = actual["counts"]
        print(f"m-fleet check ok: {c['m_files']} .m files, {c['edges']} call edges, {c['unresolved_names']} unresolved, "
              f"{c['dynamic_calls']} dynamic under example-system/matlab-repo/; {actual['backlog_items']} backlog items validate "
              f"against templates/tracker-item.json")
        return 0


# --- main -------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree", nargs="?", type=Path, help="directory holding .m files")
    ap.add_argument("--name", help="output prefix (default: the tree's folder name)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--top", type=int, default=50, help="backlog size (max 999)")
    ap.add_argument("--prefix", default="MAT", help="tracker id prefix, 2-6 upper-case letters")
    ap.add_argument("--opened", default=dt.date.today().isoformat(), help="date stamped on backlog items (YYYY-MM-DD)")
    ap.add_argument("--builtins", type=Path, help="text file with extra core/toolbox-free names, one per line (site list)")
    ap.add_argument("--dot-top", type=int, default=60, help="max nodes drawn in the DOT file (JSON map is always complete)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--fresh", action="store_true", help="ignore an existing <name>-m-migration-backlog.json instead of preserving ids and statuses")
    ap.add_argument("--check", action="store_true", help="scan example-system/matlab-repo and compare with its expected/ files")
    ap.add_argument("--write-expected", action="store_true", help="with --check: rewrite the expected files")
    a = ap.parse_args(argv)
    if a.check:
        return check(a.write_expected)
    if not a.tree:
        ap.error("tree is required unless --check")
    builtins = CORE_BUILTINS
    if a.builtins:
        builtins = builtins | frozenset(l.strip() for l in a.builtins.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))
    result = scan_tree(a.tree, builtins)
    name = a.name or safe_name(a.tree)
    paths = write_outputs(result, a.out_dir, name, a.top, a.prefix, a.opened, a.fresh, a.dot_top)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    print(json.dumps(summary, indent=2) if a.json else render_text(summary, paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
