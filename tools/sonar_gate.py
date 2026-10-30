#!/usr/bin/env python3
"""Read-only SonarQube quality gate and new-code issues summary."""

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "integrations" / "fixtures"
sys.path.insert(0, str(ROOT))
from integrations import rest_client

PAGE_SIZE = 100
SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4, "BLOCKER": 5}


def read_json(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def api_get(base: str, path: str, params: dict[str, str], token: str) -> dict:
    url = base.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    try:
        body, _ = rest_client.fetch(url, {"Authorization": f"Bearer {token}"}, dry_run=False)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(body, dict):
        raise ValueError(f"{path}: expected a JSON object response")
    return body


def get_live(base: str, token: str, project: str, branch: str | None, pull_request: str | None) -> tuple[dict, dict]:
    context = {"branch": branch} if branch else ({"pullRequest": pull_request} if pull_request else {})
    status = api_get(base, "/api/qualitygates/project_status", {"projectKey": project, **context}, token)
    issues = []
    page = 1
    while True:
        body = api_get(base, "/api/issues/search", {
            "componentKeys": project,
            "inNewCodePeriod": "true",
            "ps": str(PAGE_SIZE),
            "p": str(page),
            **context,
        }, token)
        batch = body.get("issues", [])
        if not isinstance(batch, list):
            raise ValueError("/api/issues/search: issues must be a list")
        issues.extend(batch)
        paging = body.get("paging", {})
        total = paging.get("total") if isinstance(paging, dict) else None
        if not isinstance(total, int) or page * PAGE_SIZE >= total or not batch:
            break
        page += 1
        if page > 100:
            raise ValueError("/api/issues/search: refusing to read more than 100 pages")
    return status, {"issues": issues}


def issue_severity(issue: dict) -> str:
    legacy = issue.get("severity")
    if isinstance(legacy, str) and legacy:
        return legacy.upper()
    impacts = issue.get("impacts")
    severities = [
        item.get("severity", "").upper()
        for item in impacts if isinstance(item, dict) and isinstance(item.get("severity"), str)
    ] if isinstance(impacts, list) else []
    return max(severities, key=lambda item: SEVERITY_RANK.get(item, 0), default="UNKNOWN")


def issue_type(issue: dict) -> str:
    value = issue.get("type")
    if isinstance(value, str) and value:
        return value.upper()
    impacts = issue.get("impacts")
    qualities = sorted({
        item.get("softwareQuality", "").upper()
        for item in impacts if isinstance(item, dict) and isinstance(item.get("softwareQuality"), str)
    }) if isinstance(impacts, list) else []
    return "/".join(qualities) if qualities else "UNKNOWN"


def summarize(
    status_body: dict,
    issues_body: dict,
    project: str,
    branch: str | None,
    pull_request: str | None,
    fail_on_warn: bool = False,
) -> dict:
    gate = status_body.get("projectStatus")
    if not isinstance(gate, dict):
        gate = {}
    gate_status = str(gate.get("status", "NONE")).upper()
    if gate_status not in {"OK", "ERROR", "WARN", "NONE"}:
        gate_status = "NONE"
    conditions = gate.get("conditions", [])
    if not isinstance(conditions, list):
        raise ValueError("projectStatus.conditions must be a list")
    failed = []
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        if str(condition.get("status", "")).upper() in {"ERROR", "WARN"}:
            failed.append({
                "metric": condition.get("metricKey", "unknown"),
                "status": condition.get("status"),
                "actual": condition.get("actualValue"),
                "comparator": condition.get("comparator"),
                "threshold": condition.get("errorThreshold"),
            })
    issues = issues_body.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("issues must be a list")
    normalized = []
    groups: dict[str, list[dict]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        component = issue.get("component", "unknown")
        line = issue.get("line")
        entry = {
            "key": issue.get("key", ""),
            "severity": issue_severity(issue),
            "type": issue_type(issue),
            "component": component,
            "line": line,
            "message": issue.get("message", ""),
            "impacts": issue.get("impacts", []),
        }
        normalized.append(entry)
        groups.setdefault(f"{entry['severity']}/{entry['type']}", []).append(entry)
    return {
        "project": project,
        "branch": branch,
        "pull_request": pull_request,
        "gate_status": gate_status,
        "failed_conditions": failed,
        "issue_count": len(normalized),
        "issues_by_group": groups,
        "issues": normalized,
        "pass": gate_status == "OK" or (gate_status == "WARN" and not fail_on_warn),
        "note": "Quality gate status is NONE; analysis has not produced a computed gate result." if gate_status == "NONE" else "",
    }


def markdown(summary: dict) -> str:
    context = summary["branch"] or (f"pull request {summary['pull_request']}" if summary["pull_request"] else "default analysis")
    lines = ["# SonarQube new-code gate", "", f"Project: `{summary['project']}`; context: {context}.",
             "", f"Quality gate: **{summary['gate_status']}**."]
    if summary["note"]:
        lines.extend(["", summary["note"]])
    if summary["failed_conditions"]:
        lines.extend(["", "## Failed conditions", "", "| Metric | Actual | Comparator | Threshold | Status |", "| --- | ---: | --- | ---: | --- |"])
        for item in summary["failed_conditions"]:
            lines.append(f"| {item['metric']} | {item['actual']} | {item['comparator']} | {item['threshold']} | {item['status']} |")
    lines.extend(["", f"New-code issues: **{summary['issue_count']}**."])
    for group, issues in sorted(summary["issues_by_group"].items()):
        lines.extend(["", f"## {group} ({len(issues)})", ""])
        for issue in issues:
            location = f"{issue['component']}:{issue['line']}" if issue["line"] is not None else issue["component"]
            lines.append(f"- `{location}` — {issue['message']} ({issue['key']})")
    return "\n".join(lines) + "\n"


def check() -> None:
    summary = summarize(read_json(FIXTURES / "sonar_status.json"), read_json(FIXTURES / "sonar_issues.json"),
                        "synthetic-project", None, None)
    assert summary["gate_status"] == "ERROR"
    assert len(summary["failed_conditions"]) == 1
    assert summary["issue_count"] == 2 and summary["issues"][0]["severity"] == "CRITICAL"
    assert summary["issues"][0]["type"] == "VULNERABILITY"
    assert summary["issues"][1]["type"] == "CODE_SMELL"
    warning = {"projectStatus": {"status": "WARN", "conditions": []}}
    assert summarize(warning, {"issues": []}, "p", None, None)["pass"]
    assert not summarize(warning, {"issues": []}, "p", None, None, fail_on_warn=True)["pass"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-key")
    ap.add_argument("--branch")
    ap.add_argument("--pull-request")
    ap.add_argument("--url", default=os.environ.get("SONAR_URL"))
    ap.add_argument("--status-file")
    ap.add_argument("--issues-file")
    ap.add_argument("--out", default="outputs/sonar-gate.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-warn", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        try:
            check()
            print("sonar_gate --check: OK")
            return 0
        except (AssertionError, OSError, ValueError) as exc:
            print(f"sonar_gate --check: {exc}", file=sys.stderr)
            return 2
    if bool(args.branch) and bool(args.pull_request):
        ap.error("choose either --branch or --pull-request")
    try:
        if args.status_file or args.issues_file:
            if not (args.status_file and args.issues_file):
                raise ValueError("--status-file and --issues-file must be supplied together")
            status_body, issues_body = read_json(args.status_file), read_json(args.issues_file)
        else:
            if not args.project_key:
                raise ValueError("--project-key is required for API mode")
            token = os.environ.get("SONAR_TOKEN")
            if not token:
                raise ValueError("SONAR_TOKEN is required for API mode")
            if not args.url:
                raise ValueError("--url or SONAR_URL is required for API mode")
            status_body, issues_body = get_live(args.url, token, args.project_key, args.branch, args.pull_request)
        summary = summarize(
            status_body,
            issues_body,
            args.project_key or "saved-status",
            args.branch,
            args.pull_request,
            fail_on_warn=args.fail_on_warn,
        )
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown(summary), encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"sonar_gate: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"SonarQube gate {summary['gate_status']}; {summary['issue_count']} new-code issues")
    if summary["gate_status"] == "NONE":
        return 2
    if summary["gate_status"] == "ERROR":
        return 3
    if summary["gate_status"] == "WARN" and args.fail_on_warn:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
