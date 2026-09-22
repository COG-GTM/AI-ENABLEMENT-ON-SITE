#!/usr/bin/env python3
"""Repository health check. Run after editing skills, docs, templates, or tools.

    python tools/check_repo.py

Checks:
  1. Every .devin/skills/*/SKILL.md has valid frontmatter (name matches folder, has description).
  2. Every skill listed in AGENTS.md exists, and every skill is listed in AGENTS.md.
  3. Relative links and paths mentioned in Markdown files resolve.
  4. No secrets-looking strings, forbidden words, or non-synthetic identifiers (see FORBIDDEN, SECRET_PATTERNS).
  5. JSON files parse; tracker validates; the example deck builds; what-if runs; research brief validates.
  6. example-system tests pass (Python always; C if a compiler is present); tool, REST client, and MCP server tests pass.

Exit code 0 = clean. Standard library only.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".devin" / "skills"
AGENTS = ROOT / "AGENTS.md"

# Words that must never appear (case-insensitive). Add customer/program names here before publishing.
FORBIDDEN = [
    r"\bcascade\b",
    r"\bwindsurf\b",
    r"\bdevin cloud\b(?! is not)",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"lorem ipsum",
]
SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"glpat-[A-Za-z0-9_-]{20,}",
    r"xox[abp]-[A-Za-z0-9-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"][A-Za-z0-9/+=_-]{16,}['\"]",
    r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b",  # SSN-shaped
]
SKIP_DIRS = {".git", "build", "__pycache__", "outputs"}
TEXT_EXT = {".md", ".json", ".py", ".c", ".h", ".txt", ".sh", ".yaml", ".yml", ".toml", ".cfg", ".html", ".mk", ""}

LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
BACKTICK_PATH_RE = re.compile(r"`((?:\.devin|\.agents|example-system|integrations|templates|tools|outputs)/[^`\s*]+)`")

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def iter_text_files():
    for p in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and (p.suffix in TEXT_EXT or p.name == "Makefile"):
            yield p


def parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def check_skills() -> set[str]:
    names = set()
    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir():
            continue
        f = d / "SKILL.md"
        if not f.exists():
            fail(f"{d}: missing SKILL.md")
            continue
        fm = parse_frontmatter(f.read_text())
        if fm is None:
            fail(f"{f}: missing frontmatter")
            continue
        if fm.get("name") != d.name:
            fail(f"{f}: frontmatter name {fm.get('name')!r} != folder {d.name!r}")
        if len(fm.get("description", "")) < 20:
            fail(f"{f}: description missing or too short")
        if not re.fullmatch(r"[a-z0-9-]+", d.name):
            fail(f"{d}: skill folder must be lowercase-kebab")
        names.add(d.name)
    return names


def check_agents(skill_names: set[str]) -> None:
    text = AGENTS.read_text()
    listed = set(re.findall(r"`/([a-z0-9-]+)`", text))
    for s in listed - skill_names:
        fail(f"AGENTS.md lists /{s} but .devin/skills/{s}/SKILL.md does not exist")
    for s in skill_names - listed:
        fail(f".devin/skills/{s} exists but AGENTS.md does not route to it")
    if len(text.splitlines()) > 80:
        fail("AGENTS.md is over 80 lines; move detail into a skill")


def check_links() -> None:
    for p in iter_text_files():
        if p.suffix != ".md":
            continue
        text = p.read_text(errors="replace")
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (p.parent / target).exists() and not (ROOT / target).exists():
                fail(f"{p.relative_to(ROOT)}: broken link {target}")
        for m in BACKTICK_PATH_RE.finditer(text):
            target = m.group(1).rstrip("/").split("::")[0]
            if "*" in target or "<" in target:
                continue
            if not (ROOT / target).exists() and not (p.parent / target).exists():
                fail(f"{p.relative_to(ROOT)}: path `{target}` does not exist")


def check_content() -> None:
    self_path = Path(__file__).resolve()
    for p in iter_text_files():
        if p.resolve() == self_path:
            continue
        text = p.read_text(errors="replace")
        rel = p.relative_to(ROOT)
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text, re.IGNORECASE):
                line = text.count("\n", 0, m.start()) + 1
                fail(f"{rel}:{line}: forbidden term {m.group(0)!r}")
        for pat in SECRET_PATTERNS:
            for m in re.finditer(pat, text):
                line = text.count("\n", 0, m.start()) + 1
                fail(f"{rel}:{line}: looks like a secret or identifier: {m.group(0)[:12]}...")


def run(cmd: list[str], cwd: Path = ROOT, allowed_codes: frozenset[int] = frozenset({0})) -> bool:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode not in allowed_codes:
        fail(f"{' '.join(cmd)} exited {r.returncode}:\n{r.stdout[-800:]}{r.stderr[-800:]}")
        return False
    return True


def check_tools() -> None:
    for p in iter_text_files():
        if p.suffix == ".json":
            try:
                json.loads(p.read_text())
            except json.JSONDecodeError as e:
                fail(f"{p.relative_to(ROOT)}: invalid JSON ({e})")
    py = sys.executable
    run([py, "tools/tracker_report.py"])
    run([py, "tools/what_if.py", "--imu", "imu-b"], allowed_codes=frozenset({0, 2}))  # 2 = budget FAIL, a valid result
    run([py, "tools/build_deck.py", "templates/deck-outline-example.json", "outputs/example-deck.html"])
    run([py, "tools/export_pptx.py", "templates/deck-outline-example.json", "outputs/example-deck.pptx"])
    run([py, "tools/research_brief.py", "--check"])
    run([py, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT / "example-system")
    run([py, "-m", "unittest", "discover", "-s", "tools/tests", "-q"])
    run([py, "-m", "unittest", "integrations/reference-mcp/test_server.py", "-q"])
    run([py, "-m", "unittest", "integrations/test_rest_client.py", "-q"])
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc and shutil.which("make"):
        run(["make", "-s", "test-c"], cwd=ROOT / "example-system")
    else:
        print("note: no C compiler/make found; skipped C tests")


def main() -> int:
    names = check_skills()
    check_agents(names)
    check_content()
    check_tools()  # generates outputs/ files first so check_links can see them on a clean checkout
    check_links()
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK: {len(names)} skills, links resolve, no forbidden terms, tools and tests pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
