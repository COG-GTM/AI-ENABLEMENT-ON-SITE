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
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
REQUIRED_FILES = ["AGENTS.md", "README.md", ".devin/mcp_config.json", "example-system/tracker.json"]


def default_user_mcp_config() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "devin" / "mcp_config.json"
    return Path.home() / ".config" / "devin" / "mcp_config.json"


USER_MCP_CONFIG = default_user_mcp_config()


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


def mcp_config_files() -> list[tuple[str, Path, bool]]:
    """(label, path, required) for every MCP config file Devin may load, lowest precedence first."""
    return [
        ("user mcp_config.json", USER_MCP_CONFIG, False),
        (".devin/mcp_config.json", ROOT / ".devin" / "mcp_config.json", True),
        (".devin/mcp_config.local.json", ROOT / ".devin" / "mcp_config.local.json", False),
    ]


def check_mcp_config() -> dict:
    """Validate each file's shape, then every server as the merge of its entries across files."""
    problems: list[str] = []
    checked: list[str] = []
    merged: dict[str, dict] = {}
    sources: dict[str, list[str]] = {}
    for label, f, required in mcp_config_files():
        if not required and not f.is_file():
            continue
        checked.append(label)
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{label} unreadable: {type(e).__name__}")
            continue
        servers = cfg.get("mcpServers") if isinstance(cfg, dict) else None
        if not isinstance(servers, dict) or (required and not servers):
            problems.append(f"{label}: mcpServers must be a non-empty object")
            continue
        for name, entry in servers.items():
            if not isinstance(entry, dict):
                problems.append(f"{label}: {name}: entry must be an object")
                continue
            merged[name] = {**merged.get(name, {}), **entry}
            sources.setdefault(name, []).append(label)
    for name, entry in merged.items():
        origin = "+".join(sources[name])
        problems.extend(f"{origin}: {p}" for p in server_problems({name: entry}))
    if problems:
        return row("MCP config", "FAIL", "; ".join(problems))
    return row("MCP config", "OK", f"{len(merged)} server(s): " + ", ".join(merged) + f" (checked {', '.join(checked)})")


def server_problems(servers: dict) -> list[str]:
    """Validate every mcpServers entry: local (command) or remote (url), no literal secrets."""
    problems = []
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            problems.append(f"{name}: entry must be an object")
            continue
        for field in ("env", "headers"):
            values = entry.get(field, {})
            if not isinstance(values, dict):
                problems.append(f"{name}: {field} must be an object")
                continue
            for k, v in values.items():
                if not isinstance(v, str):
                    problems.append(f"{name}: {field}.{k} must be a string")
                    continue
                if BARE_VAR_RE.match(v.strip()):
                    problems.append(f"{name}: {field}.{k} uses {v}; the documented form is ${{env:VAR}}, not ${{VAR}}")
                elif looks_like_literal_secret(k, v):
                    problems.append(f"{name}: {field}.{k} looks like a literal secret; use ${{env:VAR}} or ${{file:PATH}}")
        url = entry.get("url")
        if url is not None:
            if "command" in entry:
                problems.append(f"{name}: use either url (remote) or command (local), not both")
            elif not isinstance(url, str) or not url.startswith("https://"):
                problems.append(f"{name}: url must start with https://")
            transport = entry.get("transport", "http")
            if transport not in ("http", "sse"):
                problems.append(f"{name}: transport must be http or sse")
            continue
        cmd = entry.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            problems.append(f"{name}: missing command (or url for a remote server)")
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
    return problems


BARE_VAR_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
SECRET_KEY_RE = re.compile(r"token|secret|password|passwd|api[_-]?key|authorization", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"^(Bearer |Basic |Token )?\$\{(env|file):[^}]+\}$")


def looks_like_literal_secret(key: str, value: str) -> bool:
    if not SECRET_KEY_RE.search(key):
        return False
    v = value.strip()
    return bool(v) and not PLACEHOLDER_RE.match(v)


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


def check_optional_tools() -> dict:
    found = [name for name in ("lvkit", "cppcheck") if shutil.which(name)]
    if found:
        return row("Optional tools", "OK", ", ".join(found) + " (lvkit: LabVIEW .vi inventory; cppcheck: C static analysis)")
    return row("Optional tools", "SKIP",
               "lvkit, cppcheck not found; optional. /labview-to-python works from exported VI docs without lvkit")


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
        check_optional_tools(),
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
