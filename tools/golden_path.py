#!/usr/bin/env python3
"""Run every deterministic workflow in this repository end to end and check the results.

Usage:
    python tools/golden_path.py               # run all stages, write outputs/golden/, print a summary
    python tools/golden_path.py --json        # machine-readable summary
    python tools/golden_path.py --skip-tests  # everything except the unit-test suites (check_repo.py runs those itself)

This is the proof that the repository works on a fresh checkout with no network: readiness, research
brief, what-if analysis, tracker report, traceability matrix, executive deck (HTML and, when the exporter
is present, PPTX), the spec worked example, the MCP handshake, the model-to-code and LabVIEW-rig
equivalence checks, the host harness, and the firmware twins. Every expected number is derived from the
source files, never typed in here. Exit 1 if any stage fails.
Standard library only.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "golden"
SYSTEM = ROOT / "example-system"
PY = sys.executable
ID_RE = re.compile(r"\b[A-Z]{2,6}-(?:REQ|HAZ|BUG|CAP)-\d{3}\b")

results: list[dict] = []
progress = sys.stdout  # stderr in --json mode so stdout stays pure JSON


def record(stage: str, ok: bool, detail: str) -> bool:
    results.append({"stage": stage, "ok": ok, "detail": detail})
    print(f"{'ok  ' if ok else 'FAIL'} {stage}: {detail}", file=progress)
    return ok


def run(cmd: list[str], cwd: Path = ROOT, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- stages -----------------------------------------------------------------------------------


def stage_doctor() -> None:
    r = run([PY, "tools/doctor.py", "--json"])
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        record("doctor", False, f"no JSON on stdout (exit {r.returncode})")
        return
    failing = [c.get("check", "?") for c in d.get("checks", []) if c.get("status") == "FAIL"]
    record("doctor", r.returncode == 0 and d.get("ready") is True and not failing,
           f"ready={d.get('ready')} failing={failing or 'none'}")


def stage_research() -> None:
    src = ROOT / "templates" / "research-brief-example.json"
    brief = load(src)
    md, html = OUT / "brief.md", OUT / "brief.html"
    r1, r2 = run([PY, "tools/research_brief.py", str(src), str(md)]), run([PY, "tools/research_brief.py", str(src), str(html)])
    if r1.returncode or r2.returncode:
        record("research-brief", False, (r1.stdout + r1.stderr + r2.stdout + r2.stderr)[-300:])
        return
    n = len(brief["findings"])
    rows_md = len(re.findall(r"^\| \d+ \|", md.read_text(encoding="utf-8"), re.M))
    rows_html = html.read_text(encoding="utf-8").count("<tr><td>")
    cited = {s for f in brief["findings"] for s in f["sources"]}
    listed = {s["id"] for s in brief["sources"]}
    record("research-brief", rows_md == n == rows_html and cited <= listed,
           f"{n} findings rendered in Markdown ({rows_md}) and HTML ({rows_html}); sources cited={len(cited)} listed={len(listed)}")


def what_if(args: list[str], name: str) -> tuple[int, str]:
    out = OUT / f"what-if-{name}.md"
    r = run([PY, "tools/what_if.py", *args, "--markdown"])
    out.write_text(r.stdout, encoding="utf-8")
    m = re.search(r"-> \*\*(PASS|FAIL)\*\*", r.stdout)
    return r.returncode, m.group(1) if m else "?"


def stage_what_if() -> None:
    # The documented storyline (POWER-BUDGET.md, SN-BUG-003): today's busy-wait loop fails the budget,
    # sleep mode (25 % MCU duty) passes it, and the imu-c + CAN variant fails by a wide margin.
    a = what_if([], "baseline")
    b = what_if(["--mcu-duty", "0.25"], "with-sleep")
    c = what_if(["--imu", "imu-c", "--uplink", "can-xcvr"], "imu-c-can")
    ok = a == (2, "FAIL") and b == (0, "PASS") and c == (2, "FAIL")
    record("what-if", ok, f"baseline {a[1]} (exit {a[0]}); with sleep {b[1]} (exit {b[0]}); imu-c + CAN {c[1]} (exit {c[0]})")


def stage_tracker() -> None:
    items = load(SYSTEM / "tracker.json")["items"]
    r = run([PY, "tools/tracker_report.py", "--json"])
    md = run([PY, "tools/tracker_report.py", "--markdown"])
    (OUT / "status.md").write_text(md.stdout, encoding="utf-8")
    if r.returncode or md.returncode:
        record("tracker", False, (r.stderr + md.stderr)[-300:])
        return
    s = json.loads(r.stdout)
    by_status = sum(s["by_status"].values())
    by_type = sum(s["by_type"].values())
    ok = s["total"] == len(items) == by_status == by_type and s["open"] + s["closed"] + s["wont_fix"] == s["total"]
    record("tracker", ok, f"{s['total']} items = {len(items)} in file; by_status sums {by_status}; open {s['open']} + closed {s['closed']} + wont_fix {s['wont_fix']}")


def stage_trace_matrix() -> None:
    r = run([PY, "tools/trace_matrix.py", "--json"])
    run([PY, "tools/trace_matrix.py", "--out", str(OUT / "trace-matrix.md")])
    try:
        m = json.loads(r.stdout)
    except json.JSONDecodeError:
        record("trace-matrix", False, f"no JSON (exit {r.returncode}): {r.stderr[-200:]}")
        return
    srs_ids = set(re.findall(r"^\|\s*([A-Z]{2,6}-REQ-\d{3})\s*\|", (SYSTEM / "docs" / "SRS.md").read_text(encoding="utf-8"), re.M))
    haz_ids = set(re.findall(r"^\|\s*([A-Z]{2,6}-HAZ-\d{3})\s*\|", (SYSTEM / "docs" / "HAZARDS.md").read_text(encoding="utf-8"), re.M))
    c = m["counts"]
    ok = (r.returncode == 0 and not m["problems"] and c["untested"] == 0 and c["requirements"] == len(srs_ids)
          and c["hazards"] == len(haz_ids) and c["tested"] + c["analysis"] == c["requirements"])
    record("trace-matrix", ok, f"{c['requirements']} requirements ({len(srs_ids)} in SRS): {c['tested']} tested, "
           f"{c['analysis']} analysis, {c['untested']} untested; {c['hazards']} hazards ({len(haz_ids)} in HAZARDS); problems={m['problems'] or 'none'}")


def stage_deck() -> None:
    outline_path = ROOT / "templates" / "deck-outline-example.json"
    outline = load(outline_path)
    html = OUT / "deck.html"
    r = run([PY, "tools/build_deck.py", str(outline_path), str(html)])
    if r.returncode:
        record("exec-deck", False, (r.stdout + r.stderr)[-300:])
        return
    text = html.read_text(encoding="utf-8")
    n = len(outline["slides"])
    sections = text.count("<section")
    offline = not re.search(r"""(?:src|href)=["'](?:https?:)?//""", text)
    record("exec-deck", sections == n and offline, f"{sections} slides rendered for {n} in the outline; no external URLs={offline}")
    exporter = ROOT / "tools" / "export_pptx.py"
    if not exporter.exists():
        record("exec-deck-pptx", True, "tools/export_pptx.py not present; skipped")
        return
    pptx = OUT / "deck.pptx"
    r = run([PY, str(exporter), str(outline_path), str(pptx)])
    if r.returncode or not pptx.exists():
        record("exec-deck-pptx", False, (r.stdout + r.stderr)[-300:])
        return
    with zipfile.ZipFile(pptx) as z:
        names = set(z.namelist())
        slides = [x for x in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", x)]
        bad = z.testzip()
    ok = bad is None and "[Content_Types].xml" in names and "ppt/presentation.xml" in names and len(slides) == n
    record("exec-deck-pptx", ok, f"{len(slides)} slide parts for {n} outline slides; zip intact={bad is None}")


def stage_spec_example() -> None:
    specs = sorted(p for p in (ROOT / "specs").glob("*/") if p.is_dir())
    if not specs:
        record("spec-example", False, "no specs/<nnn>-<slug>/ folder")
        return
    srs_ids = set(ID_RE.findall((SYSTEM / "docs" / "SRS.md").read_text(encoding="utf-8")))
    haz_ids = set(ID_RE.findall((SYSTEM / "docs" / "HAZARDS.md").read_text(encoding="utf-8")))
    tracker_ids = {i["id"] for i in load(SYSTEM / "tracker.json")["items"]}
    known = srs_ids | haz_ids | tracker_ids
    problems = []
    for spec in specs:
        for name in ("spec.md", "plan.md", "tasks.md"):
            p = spec / name
            if not p.exists() or not p.read_text(encoding="utf-8").startswith("# "):
                problems.append(f"{spec.name}/{name} missing or has no title")
                continue
            text = p.read_text(encoding="utf-8")
            if name != "spec.md" and "[NEEDS CLARIFICATION]" in text:
                problems.append(f"{spec.name}/{name} still has [NEEDS CLARIFICATION] (only spec.md may)")
            new_ids = set(re.findall(r"\bnew ([A-Z]{2,6}-REQ-\d{3})\b", (spec / "spec.md").read_text(encoding="utf-8")))
            for i in set(ID_RE.findall(text)) - known - new_ids:
                if not re.search(rf"(?:new|add:?)\s+{re.escape(i)}", text):
                    problems.append(f"{spec.name}/{name} references unknown {i}")
    record("spec-example", not problems, f"{len(specs)} spec folder(s); " + ("; ".join(problems) if problems else "all IDs resolve, no open clarifications outside spec.md"))


def stage_mcp() -> None:
    handshake = ROOT / "integrations" / "reference-mcp" / "handshake.jsonl"
    requests = [json.loads(l) for l in handshake.read_text(encoding="utf-8").splitlines() if l.strip()]
    expected_ids = [q["id"] for q in requests if "id" in q]
    r = run([PY, "integrations/reference-mcp/server.py"], stdin=handshake.read_text(encoding="utf-8"))
    (OUT / "mcp-handshake.jsonl").write_text(r.stdout, encoding="utf-8")
    responses = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    ids = [p.get("id") for p in responses]
    errors = [p["id"] for p in responses if "error" in p]
    tools = next((p["result"]["tools"] for p in responses if p.get("id") == 2 and "result" in p), [])
    record("mcp-server", r.returncode == 0 and ids == expected_ids and not errors and len(tools) > 0,
           f"{len(responses)} responses for {len(expected_ids)} requests; errors={errors or 'none'}; {len(tools)} tools listed")


def compare(expected: Path, actual: Path, name: str) -> tuple[subprocess.CompletedProcess, dict | None]:
    r = run([PY, "tools/bench_compare.py", str(expected), str(actual), "--json"])
    (OUT / f"{name}-compare.md").write_text(run([PY, "tools/bench_compare.py", str(expected), str(actual), "--markdown"]).stdout, encoding="utf-8")
    try:
        return r, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r, None


def stage_model() -> None:
    # MATLAB model -> code: every golden vector row must match exactly (integer output) in the Python
    # twin, and in the C twin when a compiler is present. The skill claims both; prove both.
    vectors = SYSTEM / "model" / "filter_vectors.csv"
    n_rows = len(vectors.read_text(encoding="utf-8").splitlines()) - 1
    impls = ["python"] + (["c"] if shutil.which("cc") or shutil.which("gcc") or shutil.which("clang") else [])
    parts = []
    ok = True
    for impl in impls:
        out = OUT / f"model-{impl}.csv"
        r = run([PY, "example-system/model/run_vectors.py", "--impl", impl, "--out", str(out)])
        if r.returncode:
            record("model-to-code", False, f"{impl}: " + (r.stdout + r.stderr)[-300:])
            return
        c, j = compare(vectors, out, f"model-{impl}")
        ok = ok and c.returncode == 0 and j is not None and j["verdict"] == "PASS" and j["rows_expected"] == j["rows_actual"] == n_rows
        parts.append(f"{impl} {sum(x['pass'] for x in j['columns'])}/{len(j['columns'])} columns" if j else f"{impl} compare exit {c.returncode}")
    record("model-to-code", ok, f"{n_rows} vectors replayed through the {' and '.join(impls)} twin{'s' if len(impls) > 1 else ''}; "
           + ", ".join(parts) + " match exactly" + ("" if "c" in impls else " (no C compiler: C twin skipped)"))


def stage_bench() -> None:
    # LabVIEW rig -> Python: replay the recorded samples, compare with the VI's own results row by row.
    bench = SYSTEM / "bench"
    recording = bench / "rig_recording.csv"
    n_steps = len(recording.read_text(encoding="utf-8").splitlines()) - 1
    out = OUT / "rig-python.csv"
    r = run([PY, "example-system/bench/rig.py", "--replay", str(bench / "rig_samples.csv"), "--out", str(out)])
    if r.returncode:
        record("labview-to-python", False, (r.stdout + r.stderr)[-300:])
        return
    verdicts = [line.rsplit(",", 1)[-1] for line in out.read_text(encoding="utf-8").splitlines()[1:]]
    c, j = compare(recording, out, "rig")
    ok = (c.returncode == 0 and j is not None and j["verdict"] == "PASS" and j["rows_expected"] == j["rows_actual"] == n_steps
          and "FAIL" in verdicts)  # the recording contains a genuine failing step; the port must reproduce it
    record("labview-to-python", ok, f"{n_steps} soak steps replayed; "
           + (f"{sum(x['pass'] for x in j['columns'])}/{len(j['columns'])} columns match the VI recording; " if j else f"compare exit {c.returncode}; ")
           + f"verdicts {'/'.join(verdicts)}")


def stage_real_vi() -> None:
    # Real open-source VIs -> Python: replay the diagram-derived cases, compare with the reconstruction row by row.
    # Static + specification-level evidence only; the original VIs were never executed (see example-system/real-vi/VI-REVIEW.md).
    real = SYSTEM / "real-vi"
    cases = real / "cases.csv"
    n_cases = len(cases.read_text(encoding="utf-8").splitlines()) - 1
    out = OUT / "topic-filter-python.csv"
    n_vis = len(json.loads((real / "sources.json").read_text(encoding="utf-8"))["files"])
    r = run([PY, "example-system/real-vi/inventory.py", "--check"])
    if r.returncode:
        record("real-vi", False, (r.stdout + r.stderr)[-300:])
        return
    r = run([PY, "example-system/real-vi/topic_filter.py", "--replay", str(cases), "--out", str(out)])
    if r.returncode:
        record("real-vi", False, (r.stdout + r.stderr)[-300:])
        return
    m = re.search(r"(\d+) differ from MQTT", r.stdout)
    c, j = compare(cases, out, "topic-filter")
    ok = c.returncode == 0 and j is not None and j["verdict"] == "PASS" and j["rows_expected"] == j["rows_actual"] == n_cases and m is not None
    record("real-vi", ok, f"{n_vis} real VIs checked against sources.json; {n_cases} cases replayed; "
           + (f"{sum(x['pass'] for x in j['columns'])}/{len(j['columns'])} columns match the diagram-derived table; " if j else f"compare exit {c.returncode}; ")
           + (f"{m.group(1)} rows differ from MQTT 3.1.1 (documented)" if m else "spec-diff summary missing"))


def stage_host_harness() -> None:
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not (cc and shutil.which("make")):
        record("host-harness", True, "no C compiler/make found; skipped")
        return
    r = run(["make", "-s", "-C", "templates/host-harness", "test"])
    m = re.search(r"host tests: (\d+) checks passed", r.stdout)
    record("host-harness", r.returncode == 0 and m is not None,
           f"{m.group(1)} checks against example-system/src through hal_stub.c" if m else (r.stdout + r.stderr)[-300:])


def stage_tests() -> None:
    r = run([PY, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=SYSTEM)
    m = re.search(r"Ran (\d+) tests", r.stderr)
    record("firmware-python", r.returncode == 0, f"{m.group(1) if m else '?'} Python tests" + ("" if r.returncode == 0 else r.stderr[-300:]))
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc and shutil.which("make"):
        r = run(["make", "-s", "test-c"], cwd=SYSTEM)
        record("firmware-c", r.returncode == 0, "C twin tests pass" if r.returncode == 0 else (r.stdout + r.stderr)[-300:])
    else:
        record("firmware-c", True, "no C compiler/make found; skipped")
    for suite in (["-m", "unittest", "discover", "-s", "tools/tests", "-q"],
                  ["-m", "unittest", "integrations/reference-mcp/test_server.py", "-q"],
                  ["-m", "unittest", "integrations/test_rest_client.py", "-q"]):
        r = run([PY, *suite])
        m = re.search(r"Ran (\d+) tests", r.stderr)
        record("tests " + suite[-2], r.returncode == 0, f"{m.group(1) if m else '?'} tests" + ("" if r.returncode == 0 else r.stderr[-300:]))


# --- report -----------------------------------------------------------------------------------


def write_report() -> None:
    lines = ["# Golden path", "", f"{sum(r['ok'] for r in results)}/{len(results)} stages passed. Artifacts in `outputs/golden/`.", "",
             "| Stage | Result | Detail |", "| --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['stage']} | {'pass' if r['ok'] else 'FAIL'} | {r['detail'].replace('|', '/')} |")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-tests", action="store_true", help="skip the unit-test suites")
    a = ap.parse_args(argv)
    global progress
    progress = sys.stderr if a.json else sys.stdout
    results.clear()
    OUT.mkdir(parents=True, exist_ok=True)
    stages = [stage_doctor, stage_research, stage_what_if, stage_tracker, stage_trace_matrix, stage_deck, stage_spec_example, stage_mcp,
              stage_model, stage_bench, stage_real_vi, stage_host_harness]
    if not a.skip_tests:
        stages.append(stage_tests)
    for s in stages:
        try:
            s()
        except Exception as e:  # a crashed stage is a failed stage, not a crashed runner
            record(s.__name__.removeprefix("stage_"), False, f"{type(e).__name__}: {e}")
    write_report()
    ok = all(r["ok"] for r in results)
    if a.json:
        print(json.dumps({"ok": ok, "stages": results}, indent=2))
    else:
        print(f"\n{'OK' if ok else 'FAILED'}: {sum(r['ok'] for r in results)}/{len(results)} stages; report in {OUT.relative_to(ROOT)}/REPORT.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
