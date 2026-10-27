#!/usr/bin/env python3
"""Build/check the offline React-to-Angular walkthrough from fixture files and run evidence."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "use-cases" / "react-to-angular"
WEB = ROOT / "example-system" / "web-app"
OUT = CASE / "walkthrough.html"
MAX_BYTES = 1_500_000
PAIRS = [
    ("Component props to Angular input", "components/StatusBadge.tsx", "status-badge.component.ts", "react-badge", "angular-badge"),
    ("Controlled form to reactive form", "components/RequestForm.tsx", "request-form.component.ts", "react-form", "angular-form"),
    ("List filter and sort to computed signal", "components/RequestList.tsx", "request-list.component.ts", "react-list", "angular-list"),
    ("Custom hook to injectable service", "useRequests.ts", "request.service.ts", "react-hook", "angular-request-service"),
    ("Context to injectable settings service", "SettingsContext.tsx", "settings.service.ts", "react-context", "angular-settings"),
    ("React routes to Angular Router", "App.tsx", "app.routes.ts", "react-router", "angular-router"),
]
PROMPTS = [
    "/react-to-angular example-system/web-app/react-prototype",
    "/spec-driven Migrate the request form using the shared fixture contract",
    "/plan-to-tracker specs/002-request-form-to-angular/tasks.md --project <KEY>",
    "/tdd Port the next leaf-first unit to Angular",
    "/ui-iterate Apply the v2 request form mockup and preserve behavior",
]
ARTIFACTS = [
    "example-system/web-app/react-prototype/expected/",
    "specs/002-request-form-to-angular/",
    "outputs/request-form-to-angular-jira-payload.json (dry run)",
    "example-system/web-app/angular-app/src/ and its unit tests",
    "example-system/web-app/evidence/ (screenshots and run records)",
]
SCREENSHOTS = [
    "evidence/react-form-before-ux.png",
    "evidence/react-form.png",
    "evidence/angular-form-before-ux.png",
    "evidence/angular-form.png",
    "evidence/request-form-mockup.png",
]


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def snippet(path: Path, marker: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = f"// walkthrough:{marker}:start"
    end = f"// walkthrough:{marker}:end"
    if lines.count(start) != 1 or lines.count(end) != 1:
        raise ValueError(f"{path.relative_to(ROOT)} must contain one {start} and one {end}")
    first, last = lines.index(start), lines.index(end)
    if first >= last:
        raise ValueError(f"walkthrough marker order is invalid in {path.relative_to(ROOT)}")
    return "\n".join(lines[first + 1:last]).strip()


def markdown_steps() -> list[list[str]]:
    text = (CASE / "README.md").read_text(encoding="utf-8")
    section = text.split("## Steps", 1)[1].split("## What the fixture shows", 1)[0]
    rows = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| ---") or "Step |" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 3:
            rows.append(cells)
    if not rows:
        raise ValueError("no step rows found in the React-to-Angular use-case README")
    return rows


def evidence_block() -> str:
    parity = json.loads((WEB / "evidence" / "parity.json").read_text(encoding="utf-8"))
    ux = json.loads((WEB / "evidence" / "ux-upgrade.json").read_text(encoding="utf-8"))
    scan = json.loads((WEB / "react-prototype" / "expected" / "request-app-react-fleet-summary.json").read_text(encoding="utf-8"))
    golden_path = WEB / "evidence" / "golden-path.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.is_file() else {"status": "golden-path evidence not recorded"}
    def test_counts(run: dict) -> str:
        return f"{run['tests_passed']}/{run['tests_passed'] + run['tests_failed']}"

    rows = [
        ("React unit tests / line coverage", f"{parity['unit']['react']['tests_passed']} passed / {parity['unit']['react']['line_coverage_percent']}%"),
        ("Angular baseline unit tests / line coverage", f"{parity['unit']['angular']['tests_passed']} passed / {parity['unit']['angular']['line_coverage_percent']}%"),
        ("Angular post-UX unit tests / line coverage", f"{ux['unit']['tests_passed']} passed / {ux['unit']['line_coverage_percent']}%"),
        ("Shared e2e before UX", f"React {test_counts(parity['shared_e2e_before_ux_upgrade']['react'])}; Angular {test_counts(parity['shared_e2e_before_ux_upgrade']['angular'])}"),
        ("Shared e2e after UX", f"React {test_counts(ux['shared_e2e_after_ux_upgrade']['react'])}; Angular {test_counts(ux['shared_e2e_after_ux_upgrade']['angular'])}"),
        ("Scanner expected summary", f"{scan['counts']['files']} files; {scan['counts']['components']} components; {scan['counts']['relative_edges']} relative edges"),
        ("Golden-path run", json.dumps(golden, sort_keys=True)),
    ]
    return '<table><thead><tr><th>Evidence</th><th>Recorded result</th></tr></thead><tbody>' + "".join(
        f"<tr><td>{esc(label)}</td><td>{esc(value)}</td></tr>" for label, value in rows
    ) + "</tbody></table>"


def build() -> str:
    react = WEB / "react-prototype" / "src"
    angular = WEB / "angular-app" / "src"
    steps = markdown_steps()
    rows = []
    for index, (stage, desktop, cli) in enumerate(steps):
        prompt = PROMPTS[min(index, len(PROMPTS) - 1)]
        artifact = ARTIFACTS[min(index, len(ARTIFACTS) - 1)]
        rows.append(f"<tr><th>{esc(stage)}</th><td>{esc(desktop)}</td><td><code>{esc(cli)}</code></td>"
                    f"<td><code>{esc(prompt)}</code></td><td><code>{esc(artifact)}</code></td></tr>")
    mapping = json.loads((WEB / "react-prototype" / "expected" / "request-app-react-dependency-map.json").read_text(encoding="utf-8"))
    concept_rows = "".join(f"<tr><td>{esc(row['react'])}</td><td>{esc(row['angular'])}</td></tr>"
                           for row in mapping["concept_mappings"])
    source_pairs = []
    for title, react_path, angular_path, react_marker, angular_marker in PAIRS:
        left = snippet(react / react_path, react_marker)
        right = snippet(angular / angular_path, angular_marker)
        source_pairs.append(
            f"<section><h3>{esc(title)}</h3><div class='pair'><pre><b>React · {esc(react_path)}</b><code>{esc(left)}</code></pre>"
            f"<pre><b>Angular · {esc(angular_path)}</b><code>{esc(right)}</code></pre></div></section>"
        )
    images = []
    for relative in SCREENSHOTS:
        path = WEB / relative
        raw = base64.b64encode(path.read_bytes()).decode("ascii")
        images.append(f"<figure><img alt='{esc(relative)}' src='data:image/png;base64,{raw}'><figcaption>{esc(relative)}</figcaption></figure>")
    html_body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>React to Angular fixture walkthrough</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f8;color:#17202a;font:16px/1.55 system-ui,sans-serif}}
main{{max-width:1200px;margin:auto;padding:2rem}}h1,h2,h3{{line-height:1.2}}h1{{font-size:2.25rem}}h2{{margin-top:2.5rem;border-bottom:2px solid #3157c8;padding-bottom:.5rem}}
table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{text-align:left;vertical-align:top;border:1px solid #d6dce5;padding:.65rem}}th{{background:#edf1fa}}
code,pre{{font: .88rem/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}pre{{overflow:auto;background:#fff;border:1px solid #d6dce5;border-radius:6px;padding:1rem;white-space:pre-wrap;overflow-wrap:anywhere}}pre b{{display:block;margin-bottom:.7rem;color:#3157c8}}pre code{{white-space:pre-wrap}}
.shots{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}}figure{{margin:0;background:#fff;padding:.75rem;border:1px solid #d6dce5}}img{{display:block;width:100%;height:auto}}figcaption{{font-size:.8rem;margin-top:.5rem;overflow-wrap:anywhere}}
.note{{padding:1rem;background:#fff3cd;border-left:4px solid #d99b00}}@media(max-width:800px){{.pair{{grid-template-columns:1fr}}main{{padding:1rem}}}}
</style></head><body><main>
<h1>React prototype to Angular: runnable fixture walkthrough</h1>
<p>Generated from the use-case README, scanner expected outputs, marked source snippets, and committed run evidence.
The paired apps use synthetic equipment service requests.</p>
<h2>Stages, prompts, and artifacts</h2><table><thead><tr><th>Stage</th><th>Desktop action</th><th>CLI command</th><th>Prompt</th><th>Artifact left behind</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>React to Angular concept map</h2><table><thead><tr><th>React concept</th><th>Angular target</th></tr></thead><tbody>{concept_rows}</tbody></table>
<h2>Paired source snippets</h2>{''.join(source_pairs)}
<h2>Run evidence</h2>{evidence_block()}
<p class="note">Screenshots are embedded PNGs from Playwright runs. They show captured appearance only; the tests prove only their specified fixture flows. Preview availability in an offline or FedRAMP environment is confirm on your build.</p>
<h2>Playwright screenshots</h2><div class="shots">{''.join(images)}</div>
</main></body></html>
"""
    if len(html_body.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"walkthrough is {len(html_body.encode('utf-8'))} bytes; maximum is {MAX_BYTES}")
    return html_body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = build()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"build_walkthrough: {exc}", file=sys.stderr)
        return 2
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != output:
            print(f"walkthrough stale: run `python tools/build_walkthrough.py --write`", file=sys.stderr)
            return 1
        print(f"walkthrough fresh: {len(output.encode('utf-8'))} bytes")
        return 0
    OUT.write_text(output, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(output.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
