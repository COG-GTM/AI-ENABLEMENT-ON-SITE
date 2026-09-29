#!/usr/bin/env python3
"""Journaled, resumable migration pipeline: scan -> pack -> agent -> compare -> report, for one tree in one language.

    python tools/pipeline_run.py --lang c      --tree example-system/firmware-repo --name firmware-repo
    python tools/pipeline_run.py --lang matlab --tree example-system/matlab-repo   --name matlab-repo
    python tools/pipeline_run.py --lang labview --tree example-system              --name fleet
        [--out outputs/pipeline/<name>] [--budget 8000] [--limit N] [--resume] [--from-stage pack]
        [--agent-cmd 'cmd {pack} {results} {id} {unit} {tree}'] [--compare-cmd 'cmd {results} {id} {unit} {tree}'] [--json]

This is the file a team owns in its repository and runs from a laptop, a cron job, or a CI runner. It is deterministic
glue around the scanners and tools/prompt_pack.py; it does not contain migration logic and it does not call any agent
unless told to.

Stages (each appends to <out>/journal.jsonl and updates <out>/state.json; a stage that already completed on identical
inputs is skipped when --resume is given):
  scan     tools/<lang>_fleet_scan.py <tree> --name <name> --out-dir <out>/scan        (inventory, dependency map, backlog)
  pack     tools/prompt_pack.py --map <out>/scan/<name>-dependency-map.json          (one bounded pack per backlog unit)
  agent    for each pack, in leaf-first order, up to --limit:
             with --agent-cmd: run it with the placeholders filled; it must write <results>/<id>/result.json (shape in the pack)
             without:          record `skipped: no --agent-cmd (dry run)` - nothing is invented, no result.json is written
           a unit whose result.json already says done/blocked is not re-run (delete it to redo)
  compare  for each result.json with status done: with --compare-cmd run it (exit 0 = proven), else check that every file
           listed under `evidence` exists; done without evidence is reported as `unproven`
  report   <out>/REPORT.md (table per unit), <out>/state.json, and <out>/<name>-backlog-status.json: the scan's backlog with
           status moved to in_review for units whose proof passed (tools/tracker_report.py --file reads it). Statuses are
           never moved to closed by this tool - a person does that.

Placeholders for --agent-cmd / --compare-cmd: {pack} pack file, {results} results dir for the unit, {id}, {unit} tree-relative
path, {tree} absolute tree path, {out} pipeline dir. The command runs through the shell; quote it as one argument.

Offline by default: no network, no agent, no writes outside <out>. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

from fleet_common import ROOT, OUT_DIR, rel

TOOL = "tools/pipeline_run.py"
PY = sys.executable
SCANNERS = {"c": "tools/c_fleet_scan.py", "matlab": "tools/m_fleet_scan.py", "labview": "tools/vi_fleet_scan.py"}
SUFFIX = {"c": "-c", "matlab": "-m", "labview": ""}   # scanner output name infix: <name>-c-..., <name>-m-..., <name>-...
STAGES = ["scan", "pack", "agent", "compare", "report"]


class Pipeline:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.tree = a.tree.resolve()
        self.out = (a.out or (OUT_DIR / "pipeline" / a.name)).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.journal = self.out / "journal.jsonl"
        self.state_path = self.out / "state.json"
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if a.resume and self.state_path.is_file() else \
            {"tool": TOOL, "name": a.name, "lang": a.lang, "tree": str(self.tree), "stages": {}}
        self.scan_dir = self.out / "scan"
        self.pack_dir = self.out / "packs"
        self.results = self.out / "results"
        self.prefix = f"{a.name}{SUFFIX[a.lang]}"

    # -- journal -----------------------------------------------------------------------------------------------
    def log(self, stage: str, event: str, **kw) -> None:
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "stage": stage, "event": event, **kw}
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        if not self.a.json:
            extra = " ".join(f"{k}={v}" for k, v in kw.items() if k not in ("stdout",))
            print(f"[{stage}] {event} {extra}".rstrip(), file=sys.stderr)

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def done(self, stage: str, inputs_hash: str, **info) -> None:
        self.state["stages"][stage] = {"status": "done", "inputs_hash": inputs_hash, "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **info}
        self.save()

    def skip_if_done(self, stage: str, inputs_hash: str) -> bool:
        st = self.state["stages"].get(stage)
        if self.a.resume and st and st.get("status") == "done" and st.get("inputs_hash") == inputs_hash and stage not in self.forced:
            self.log(stage, "skipped", reason="already done on identical inputs (--resume)")
            return True
        return False

    @property
    def forced(self) -> set[str]:
        if not self.a.from_stage:
            return set()
        return set(STAGES[STAGES.index(self.a.from_stage):])

    # -- hashing -------------------------------------------------------------------------------------------------
    def tree_hash(self) -> str:
        h = hashlib.sha256()
        for p in sorted(x for x in self.tree.rglob("*") if x.is_file() and ".git" not in x.parts):
            st = p.stat()
            h.update(f"{p.relative_to(self.tree).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
        return h.hexdigest()[:16]

    @staticmethod
    def file_hash(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else "missing"

    # -- stages ---------------------------------------------------------------------------------------------------
    def run(self, cmd: list[str], stage: str) -> subprocess.CompletedProcess:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            self.log(stage, "failed", cmd=" ".join(shlex.quote(c) for c in cmd), stderr=(r.stderr or r.stdout)[-400:])
            raise SystemExit(f"{stage} failed; see {rel(self.journal)}")
        return r

    def stage_scan(self) -> None:
        ih = self.tree_hash()
        if self.skip_if_done("scan", ih):
            return
        self.log("scan", "start", tree=str(self.tree), scanner=SCANNERS[self.a.lang])
        cmd = [PY, SCANNERS[self.a.lang], str(self.tree), "--name", self.a.name, "--out-dir", str(self.scan_dir), "--json"]
        if self.a.opened:
            cmd += ["--opened", self.a.opened]
        r = self.run(cmd, "scan")
        summary = json.loads(r.stdout)
        outputs = summary.get("outputs", {})
        self.done("scan", ih, counts=summary.get("counts", {}), classification=summary.get("classification", {}), outputs=outputs)
        self.log("scan", "done", **{k: v for k, v in summary.get("classification", {}).items()})

    @property
    def map_path(self) -> Path:
        return self.scan_dir / f"{self.prefix}-dependency-map.json"

    @property
    def backlog_path(self) -> Path:
        return self.scan_dir / f"{self.prefix}-migration-backlog.json"

    def stage_pack(self) -> None:
        ih = self.file_hash(self.map_path) + self.file_hash(self.backlog_path) + f"|{self.a.budget}"
        if self.skip_if_done("pack", ih):
            return
        self.log("pack", "start", map=str(rel(self.map_path)), budget=self.a.budget)
        cmd = [PY, "tools/prompt_pack.py", "--map", str(self.map_path), "--out-dir", str(self.pack_dir), "--name", self.a.name, "--budget", str(self.a.budget), "--json"]
        if self.a.task_file:
            cmd += ["--task-file", str(self.a.task_file)]
        r = self.run(cmd, "pack")
        manifest = json.loads(r.stdout)
        t = manifest["totals"]
        self.done("pack", ih, packs=t["packs"], tokens_est=t["tokens_est"], max_pack_tokens_est=t["max_pack_tokens_est"], over_budget=t["over_budget"],
                  whole_tree_tokens_est=manifest["whole_tree"]["tokens_est"])
        self.log("pack", "done", packs=t["packs"], max_tokens=t["max_pack_tokens_est"], whole_tree_tokens=manifest["whole_tree"]["tokens_est"])

    def packs(self) -> list[dict]:
        return json.loads((self.pack_dir / "manifest.json").read_text(encoding="utf-8"))["packs"]

    def result_of(self, pack_id: str) -> dict | None:
        p = self.results / pack_id / "result.json"
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"status": "failed", "notes": "result.json is not valid JSON"}

    def fill(self, template: str, pack: dict) -> str:
        return template.format(pack=str(ROOT / pack["file"]) if not Path(pack["file"]).is_absolute() else pack["file"],
                               results=str(self.results / pack["id"]), id=pack["id"], unit=pack["unit"], tree=str(self.tree), out=str(self.out))

    def stage_agent(self) -> None:
        packs = self.packs()[: self.a.limit or None]
        mode = "external command" if self.a.agent_cmd else "dry run"
        self.log("agent", "start", mode=mode, packs=len(packs), limit=self.a.limit or "none")
        agent_state = self.state["stages"].setdefault("agent", {"status": "running", "units": {}})
        agent_state["status"], agent_state["mode"] = "running", mode
        for pack in packs:
            pid = pack["id"]
            existing = self.result_of(pid)
            if existing and existing.get("status") in ("done", "blocked"):
                agent_state["units"][pid] = {"status": existing["status"], "source": "existing result.json"}
                self.log("agent", "kept", id=pid, status=existing["status"])
                continue
            if not self.a.agent_cmd:
                agent_state["units"][pid] = {"status": "skipped", "reason": "no --agent-cmd (dry run)"}
                self.log("agent", "skipped", id=pid, reason="no --agent-cmd (dry run)")
                continue
            (self.results / pid).mkdir(parents=True, exist_ok=True)
            cmd = self.fill(self.a.agent_cmd, pack)
            self.log("agent", "run", id=pid, cmd=cmd)
            t0 = time.time()
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
            (self.results / pid / "agent-stdout.txt").write_text(r.stdout, encoding="utf-8")
            (self.results / pid / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            res = self.result_of(pid)
            status = res.get("status", "failed") if res else "failed"
            if r.returncode and status == "done":
                status = "failed"
            if res is None:
                self.log("agent", "no result.json", id=pid, exit=r.returncode)
            agent_state["units"][pid] = {"status": status, "exit": r.returncode, "seconds": round(time.time() - t0, 1)}
            self.log("agent", "finished", id=pid, status=status, exit=r.returncode)
            self.save()
        agent_state["status"] = "done"
        agent_state["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self.save()
        self.log("agent", "done", **{k: sum(1 for u in agent_state["units"].values() if u["status"] == k) for k in ("done", "blocked", "failed", "skipped")})

    def stage_compare(self) -> None:
        packs = self.packs()
        cmp_state = self.state["stages"].setdefault("compare", {"status": "running", "units": {}})
        cmp_state["status"] = "running"
        cmp_state["mode"] = "external command" if self.a.compare_cmd else "evidence files exist"
        self.log("compare", "start", mode=cmp_state["mode"])
        for pack in packs:
            pid = pack["id"]
            res = self.result_of(pid)
            if not res:
                cmp_state["units"][pid] = {"status": "no result"}
                continue
            if res.get("status") != "done":
                cmp_state["units"][pid] = {"status": res.get("status", "failed"), "blocked_on": res.get("blocked_on")}
                continue
            evidence = res.get("evidence") or []
            if self.a.compare_cmd:
                cmd = self.fill(self.a.compare_cmd, pack)
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
                (self.results / pid / "compare-output.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
                cmp_state["units"][pid] = {"status": "proven" if r.returncode == 0 else "failed", "exit": r.returncode, "evidence": evidence}
            else:
                missing = [e for e in evidence if not (ROOT / e).is_file() and not (self.results / pid / e).is_file() and not Path(e).is_file()]
                cmp_state["units"][pid] = {"status": "unproven" if (not evidence or missing) else "evidence present",
                                           "evidence": evidence, "missing": missing}
            self.log("compare", "unit", id=pid, status=cmp_state["units"][pid]["status"])
        cmp_state["status"] = "done"
        self.save()
        self.log("compare", "done", **{k: sum(1 for u in cmp_state["units"].values() if u["status"] == k)
                                         for k in ("proven", "evidence present", "unproven", "failed", "blocked", "no result")})

    def stage_report(self) -> None:
        packs = self.packs()
        agent = self.state["stages"].get("agent", {}).get("units", {})
        comp = self.state["stages"].get("compare", {}).get("units", {})
        scan = self.state["stages"].get("scan", {})
        pack_st = self.state["stages"].get("pack", {})
        lines = [f"# Pipeline report: {self.a.name} ({self.a.lang})", "",
                 f"Generated by `{TOOL}`; tree `{self.tree}`; journal `{rel(self.journal)}`. "
                 f"Agent stage mode: **{self.state['stages'].get('agent', {}).get('mode', 'not run')}**; compare mode: "
                 f"**{self.state['stages'].get('compare', {}).get('mode', 'not run')}**.", "",
                 "## Scan", "", f"- counts: {json.dumps(scan.get('counts', {}), sort_keys=True)}",
                 f"- classification: {json.dumps(scan.get('classification', {}), sort_keys=True)}", "",
                 "## Packs", "",
                 f"- {pack_st.get('packs', 0)} packs, {pack_st.get('tokens_est', 0)} tokens est. total, largest {pack_st.get('max_pack_tokens_est', 0)}, "
                 f"{pack_st.get('over_budget', 0)} over the {self.a.budget} budget; whole tree {pack_st.get('whole_tree_tokens_est', 0)} tokens est.",
                 f"- index: `{rel(self.pack_dir / 'INDEX.md')}`", "",
                 "## Units", "", "| # | id | unit | class | pack tokens | agent | proof | notes |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        counts = {"done": 0, "blocked": 0, "failed": 0, "skipped": 0, "proven": 0}
        for i, p in enumerate(packs, 1):
            a_st = agent.get(p["id"], {}).get("status", "not run")
            c_st = comp.get(p["id"], {}).get("status", "not run")
            res = self.result_of(p["id"]) or {}
            note = res.get("blocked_on") or res.get("notes", "") or ""
            counts[a_st] = counts.get(a_st, 0) + 1
            if c_st in ("proven", "evidence present"):
                counts["proven"] += 1
            lines.append(f"| {i} | `{p['id']}` | `{p['unit']}` | {p['classification']} | {p['tokens_est']} | {a_st} | {c_st} | {str(note)[:80]} |")
        lines += ["", "## Totals", "",
                  f"- agent: {counts.get('done', 0)} done, {counts.get('blocked', 0)} blocked, {counts.get('failed', 0)} failed, {counts.get('skipped', 0)} skipped (dry run)",
                  f"- proof: {counts['proven']} units with a passing comparison or present evidence; everything else is unproven",
                  "", "## Next", "",
                  f"- status view: `python tools/tracker_report.py --file {rel(self.out / (self.a.name + '-backlog-status.json'))}`",
                  f"- re-run only what changed: `python {TOOL} --lang {self.a.lang} --tree {rel(self.tree) if str(self.tree).startswith(str(ROOT)) else self.tree} --name {self.a.name} --resume`",
                  "- a unit is finished when a person reads its evidence and moves the tracker item to `closed`; this tool never does that", ""]
        (self.out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        # backlog with statuses from the proof stage
        if self.backlog_path.is_file():
            backlog = json.loads(self.backlog_path.read_text(encoding="utf-8"))
            moved = 0
            for it in backlog["items"]:
                c_st = comp.get(it["id"], {}).get("status")
                if c_st in ("proven", "evidence present") and it["status"] == "proposed":
                    it["status"] = "in_review"
                    it["notes"] = f"pipeline {self.a.name}: proof {c_st}; see {rel(self.results / it['id'])}. " + it["notes"]
                    moved += 1
            backlog["_about"] = f"Copy of {rel(self.backlog_path)} with statuses from {TOOL} ({moved} moved to in_review). " + backlog.get("_about", "")
            (self.out / f"{self.a.name}-backlog-status.json").write_text(json.dumps(backlog, indent=2) + "\n", encoding="utf-8")
        self.state["stages"]["report"] = {"status": "done", "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "report": str(rel(self.out / "REPORT.md")), **counts}
        self.save()
        self.log("report", "done", report=str(rel(self.out / "REPORT.md")), **counts)

    def go(self) -> dict:
        start = STAGES.index(self.a.from_stage) if self.a.from_stage else 0
        for stage in STAGES[start:]:
            getattr(self, f"stage_{stage}")()
            if self.a.until and stage == self.a.until:
                break
        return self.state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", required=True, choices=sorted(SCANNERS))
    ap.add_argument("--tree", required=True, type=Path)
    ap.add_argument("--name", required=True, help="scan/pack/pipeline name (also the tracker backlog name)")
    ap.add_argument("--out", type=Path, help="pipeline directory (default outputs/pipeline/<name>)")
    ap.add_argument("--budget", type=int, default=8000, help="per-pack token budget (est.)")
    ap.add_argument("--limit", type=int, default=0, help="run the agent stage on at most N packs (0 = all)")
    ap.add_argument("--agent-cmd", help="shell command per pack with {pack} {results} {id} {unit} {tree} {out}; omitted = dry run")
    ap.add_argument("--compare-cmd", help="shell command per done unit with {results} {id} {unit} {tree} {out}; exit 0 = proven")
    ap.add_argument("--task-file", type=Path, help="passed to prompt_pack.py")
    ap.add_argument("--opened", help="date stamped on new backlog items (YYYY-MM-DD); default today")
    ap.add_argument("--resume", action="store_true", help="skip stages already done on identical inputs; keep existing result.json files")
    ap.add_argument("--from-stage", choices=STAGES, help="start here (earlier stages must have run before)")
    ap.add_argument("--until", choices=STAGES, help="stop after this stage")
    ap.add_argument("--json", action="store_true", help="print state.json instead of progress lines")
    a = ap.parse_args(argv)
    if not a.tree.is_dir():
        raise SystemExit(f"{a.tree} is not a directory")
    state = Pipeline(a).go()
    if a.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        rep = state["stages"].get("report", {})
        print(f"{a.name}: stages {', '.join(f'{k}={v.get('status')}' for k, v in state['stages'].items())}; report {rep.get('report', '(not run)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
