#!/usr/bin/env python3
"""Two-second readiness check for this repository on a new laptop.

    python tools/doctor.py          # table
    python tools/doctor.py --json   # machine-readable

Prints one row per prerequisite: OK, SKIP (optional, missing), or FAIL (required, missing).
Exit code 0 unless something required failed. Never touches the network. Standard library only.
"""

import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
REQUIRED_FILES = ["AGENTS.md", "README.md", ".devin/mcp_config.json", "example-system/tracker.json"]


def row(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail}


def check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    return row("Python", "OK" if ok else "FAIL",
               f"{v.major}.{v.minor}.{v.micro} at {sys.executable}" + ("" if ok else f" (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"))


def check_files() -> dict:
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
    if missing:
        return row("Repository files", "FAIL", "missing: " + ", ".join(missing))
    return row("Repository files", "OK", f"root {ROOT}")


def check_skills() -> dict:
    d = ROOT / ".devin" / "skills"
    if not d.is_dir():
        return row("Skills", "FAIL", ".devin/skills/ not found")
    names = sorted(p.name for p in d.iterdir() if (p / "SKILL.md").is_file())
    if not names:
        return row("Skills", "FAIL", "no SKILL.md files under .devin/skills/")
    return row("Skills", "OK", f"{len(names)} found: " + ", ".join(names))


def check_mcp_config() -> dict:
    f = ROOT / ".devin" / "mcp_config.json"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return row("MCP config", "FAIL", f"{f.relative_to(ROOT)} unreadable: {type(e).__name__}")
    servers = cfg.get("mcpServers") if isinstance(cfg, dict) else None
    if not isinstance(servers, dict) or not servers:
        return row("MCP config", "FAIL", "mcpServers must be a non-empty object")
    problems = []
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            problems.append(f"{name}: entry must be an object")
            continue
        cmd = entry.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            problems.append(f"{name}: missing command")
            continue
        if not resolve_command(cmd):
            problems.append(f"{name}: command {cmd!r} not found on PATH")
        args = entry.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            problems.append(f"{name}: args must be a list of strings")
            continue
        for a in args:
            if a.endswith(".py") and not (ROOT / a).exists():
                problems.append(f"{name}: {a} not found")
    if problems:
        return row("MCP config", "FAIL", "; ".join(problems))
    return row("MCP config", "OK", f"{len(servers)} server(s): " + ", ".join(servers))


def resolve_command(cmd: str) -> bool:
    if os.sep in cmd or "/" in cmd:
        p = Path(cmd) if Path(cmd).is_absolute() else ROOT / cmd
        return p.is_file() and os.access(p, os.X_OK)
    return shutil.which(cmd) is not None


def check_outputs_writable() -> dict:
    d = ROOT / "outputs"
    if d.exists() and not d.is_dir():
        return row("outputs/ writable", "FAIL", "outputs exists but is not a directory")
    target = d if d.is_dir() else ROOT
    try:
        with tempfile.NamedTemporaryFile(dir=target, prefix=".doctor-", delete=True):
            pass
    except OSError as e:
        return row("outputs/ writable", "FAIL", type(e).__name__)
    note = "" if d.is_dir() else " (not created yet; tools create it on first run)"
    return row("outputs/ writable", "OK", "outputs/" + note)


def check_c_toolchain() -> dict:
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    make = shutil.which("make")
    if cc and make:
        return row("C compiler + make", "OK", f"{Path(cc).name}, {Path(make).name} (C firmware tests will run)")
    have = [Path(x).name for x in (cc, make) if x]
    return row("C compiler + make", "SKIP",
               "optional; Python firmware twin covers the same behaviour" + (f" (found: {', '.join(have)})" if have else ""))


def check_network() -> dict:
    return row("Network", "OK", "not required; every workflow runs offline against example-system/")


def check_platform() -> dict:
    return row("Platform", "OK", f"{platform.system()} {platform.release()}, cwd {Path.cwd()}")


def run_all() -> list[dict]:
    return [
        check_platform(),
        check_python(),
        check_files(),
        check_skills(),
        check_mcp_config(),
        check_outputs_writable(),
        check_c_toolchain(),
        check_network(),
    ]


def render(rows: list[dict]) -> str:
    w = max(len(r["check"]) for r in rows)
    lines = [f"{r['status']:<4} {r['check']:<{w}}  {r['detail']}" for r in rows]
    fails = sum(r["status"] == "FAIL" for r in rows)
    skips = sum(r["status"] == "SKIP" for r in rows)
    verdict = "READY" if not fails else f"NOT READY ({fails} required check(s) failed)"
    lines.append(f"\n{verdict}; {skips} optional item(s) skipped. Next: python tools/check_repo.py")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if any(a not in ("--json",) for a in argv):
        print(__doc__.strip())
        return 2
    rows = run_all()
    if "--json" in argv:
        print(json.dumps({"ready": all(r["status"] != "FAIL" for r in rows), "checks": rows}, indent=2))
    else:
        print(render(rows))
    return 0 if all(r["status"] != "FAIL" for r in rows) else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main(sys.argv[1:]))
