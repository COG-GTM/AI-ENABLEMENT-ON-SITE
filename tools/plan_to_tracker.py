#!/usr/bin/env python3
"""Convert spec-driven tasks to Jira v2 issue payloads; writes are opt-in."""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_RE = re.compile(r"^\s*-\s+\[(?: |x|X)\]\s+(T\d+\.\d+)\s+(.+?)\s*$")
SPEC_RE = re.compile(r"^(?P<number>\d{3})-(?P<slug>[a-z0-9-]+)$")
TEST_RE = re.compile(r"`([^`]*(?:test|make|check)[^`]*)`", re.IGNORECASE)
DEFAULT_SPEC = ROOT / "specs" / "001-diagnostics-packet" / "tasks.md"


def parse_tasks(path: Path) -> tuple[str, str, list[dict]]:
    match = SPEC_RE.match(path.parent.name)
    if not match:
        raise ValueError("tasks file must be under specs/<nnn>-<slug>/")
    content = path.read_text(encoding="utf-8-sig")
    tasks = []
    for line in content.splitlines():
        found = TASK_RE.match(line)
        if not found:
            continue
        task_id, text = found.groups()
        test = TEST_RE.search(text)
        acceptance = test.group(1) if test else "Complete this task and run the named verification for its workstream."
        summary = f"{task_id} {text}"
        tasks.append({"id": task_id, "text": text, "summary": summary, "acceptance": acceptance})
    if not tasks:
        raise ValueError(f"no spec-driven task rows found in {path}")
    return match.group("number"), match.group("slug"), tasks


def make_payloads(path: Path, project: str, issue_type: str) -> dict:
    number, slug, tasks = parse_tasks(path)
    spec_dir = path.parent
    spec_path = (spec_dir / "spec.md").as_posix()
    plan_path = (spec_dir / "plan.md").as_posix()
    label = f"spec-{number}"
    issues = []
    for task in tasks:
        branch = f"feature/<KEY-placeholder>-{slug}"
        description = (
            f"Task {task['id']}: {task['text']}\n\n"
            f"Spec: {spec_path}\n"
            f"Plan: {plan_path}\n"
            f"Acceptance/test: {task['acceptance']}\n"
            f"Suggested branch: {branch}\n"
            "Assignee: set by the owner in Jira."
        )
        issues.append({
            "task_id": task["id"],
            "branch": branch,
            "payload": {
                "fields": {
                    "project": {"key": project},
                    "issuetype": {"name": issue_type},
                    "summary": task["summary"],
                    "description": description,
                    "labels": [label],
                }
            },
            "created_key": None,
        })
    return {
        "spec": spec_dir.name,
        "tasks_file": path.as_posix(),
        "spec_path": spec_path,
        "plan_path": plan_path,
        "project": project,
        "issue_type": issue_type,
        "assignee_note": "Assignee is empty; set by the owner in Jira.",
        "issues": issues,
    }


def csv_content(document: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Project key", "Issue Type", "Summary", "Description", "Labels", "Assignee"])
    for item in document["issues"]:
        fields = item["payload"]["fields"]
        writer.writerow([
            fields["project"]["key"], fields["issuetype"]["name"], fields["summary"],
            fields["description"], ",".join(fields["labels"]), "",
        ])
    return stream.getvalue()


def safe_target(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1")


def write_issues(document: dict, base: str, token: str, output: Path) -> None:
    if not safe_target(base):
        raise ValueError("refusing non-HTTPS Jira URL; plain HTTP is allowed only to 127.0.0.1")
    endpoint = base.rstrip("/") + "/rest/api/2/issue"
    for item in document["issues"]:
        body = json.dumps(item["payload"]).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                created = json.load(response)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise ValueError(f"Jira returned HTTP {exc.code}; response body omitted") from None
        except urllib.error.URLError as exc:
            raise ValueError(f"Jira connection failed: {exc.reason}") from None
        key = created.get("key") if isinstance(created, dict) else None
        if not isinstance(key, str) or not key:
            raise ValueError("Jira response did not contain an issue key")
        item["created_key"] = key
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def check() -> None:
    first = make_payloads(DEFAULT_SPEC, "SN", "Task")
    second = make_payloads(DEFAULT_SPEC, "SN", "Task")
    assert first == second
    assert len(first["issues"]) == 15
    assert first["issues"][0]["payload"]["fields"]["labels"] == ["spec-001"]
    assert "set by the owner in Jira" in first["issues"][0]["payload"]["fields"]["description"]
    assert first["issues"][0]["branch"] == "feature/<KEY-placeholder>-diagnostics-packet"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="?", default=str(DEFAULT_SPEC))
    parser.add_argument("--project", default="SN")
    parser.add_argument("--type", default="Task")
    parser.add_argument("--out")
    parser.add_argument("--csv", nargs="?", const=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        try:
            check()
            print("plan_to_tracker --check: OK")
            return 0
        except (AssertionError, OSError, ValueError) as exc:
            print(f"plan_to_tracker --check: {exc}", file=sys.stderr)
            return 2
    try:
        tasks_path = Path(args.tasks)
        document = make_payloads(tasks_path, args.project, args.type)
        slug = SPEC_RE.match(tasks_path.parent.name).group("slug")
        output = Path(args.out) if args.out else Path("outputs") / f"{slug}-jira-payload.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        if args.csv is not None:
            csv_path = (Path("outputs") / f"{slug}-jira-payload.csv") if args.csv is True else Path(args.csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text(csv_content(document), encoding="utf-8", newline="")
        if args.apply:
            base = os.environ.get("JIRA_URL")
            token = os.environ.get("JIRA_TOKEN")
            if not base or not token:
                raise ValueError("--apply requires JIRA_URL and JIRA_TOKEN")
            if not safe_target(base):
                raise ValueError("refusing non-HTTPS Jira URL; plain HTTP is allowed only to 127.0.0.1")
            print(f"Ready to create {len(document['issues'])} Jira issues.")
            if not args.yes:
                if input("Type yes to continue: ") != "yes":
                    print("Cancelled; no Jira issues were created.")
                    return 0
            write_issues(document, base, token, output)
            print(f"Created {len(document['issues'])} Jira issues; keys saved to {output}.")
        else:
            print(f"Dry run: {len(document['issues'])} Jira issue payloads written to {output}.")
            if args.csv is not None:
                print(f"CSV written to {csv_path}.")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"plan_to_tracker: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
