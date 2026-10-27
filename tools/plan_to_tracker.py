#!/usr/bin/env python3
"""Convert spec-driven tasks to Jira v2 issue payloads; writes are opt-in."""

import argparse
import csv
import hashlib
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


def canonical_payload(item: dict) -> bytes:
    return json.dumps(
        item["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def payload_sha256(item: dict) -> str:
    return hashlib.sha256(canonical_payload(item)).hexdigest()


def stale_note(item: dict) -> str:
    return f"{item['task_id']} ({item['created_key']}) changed since posting; update the issue in Jira by hand"


def stale_notes(document: dict) -> list[str]:
    return [stale_note(item) for item in document["issues"] if item.get("stale") and item.get("created_key")]


def csv_content(document: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Project key", "Issue Type", "Summary", "Description", "Labels", "Assignee", "Note"])
    for item in document["issues"]:
        fields = item["payload"]["fields"]
        writer.writerow([
            fields["project"]["key"], fields["issuetype"]["name"], fields["summary"],
            fields["description"], ",".join(fields["labels"]), "", stale_note(item) if item.get("stale") else "",
        ])
    return stream.getvalue()


def markdown_content(document: dict) -> str:
    notes = stale_notes(document)
    lines = [
        "# Jira payload review",
        "",
        f"- Spec: `{document['spec']}`",
        f"- Project: `{document['project']}`",
        "",
        "## Tasks changed since posting",
        "",
    ]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("No posted task payloads changed since posting.")
    return "\n".join(lines) + "\n"


def safe_target(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1")


def normalize_jira_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("JIRA_URL must include a scheme and host")
    if parsed.username or parsed.password:
        raise ValueError("JIRA_URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("JIRA_URL must not include a query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("JIRA_URL has an invalid port") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host + (f":{port}" if port is not None else "")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def saved_state(document: dict, output: Path) -> dict:
    if not output.exists():
        return document
    try:
        existing = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read existing payload state from {output}: {exc}") from exc
    if not isinstance(existing, dict):
        raise ValueError(f"existing payload state in {output} is not an object")
    if "jira_url" in existing:
        document["jira_url"] = existing["jira_url"]

    def identity(parent: dict, item: dict) -> tuple[str, str, str]:
        fields = item.get("payload", {}).get("fields", {})
        project = fields.get("project", {}).get("key", parent.get("project", ""))
        return str(project), str(parent.get("spec", "")), str(item.get("task_id", ""))

    previous = {
        identity(existing, item): item
        for item in existing.get("issues", [])
        if isinstance(item, dict)
    }
    for item in document["issues"]:
        old = previous.get(identity(document, item))
        if old is None:
            continue
        if old.get("created_key"):
            item["created_key"] = old["created_key"]
            posted_hash = old.get("posted_payload_sha256") or old.get("posted_sha256")
            if posted_hash:
                item["posted_payload_sha256"] = posted_hash
                item["posted_sha256"] = old.get("posted_sha256", posted_hash)
                if payload_sha256(item) != posted_hash:
                    item["stale"] = True
        if old.get("posting"):
            item["posting"] = True
    return document


def persist(document: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(markdown_content(document), encoding="utf-8")


def write_csv(document: dict, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(csv_content(document), encoding="utf-8", newline="")


def write_issues(document: dict, base: str, token: str, output: Path) -> None:
    if not safe_target(base):
        raise ValueError("refusing non-HTTPS Jira URL; plain HTTP is allowed only to 127.0.0.1")
    if any(item.get("posting") and not item.get("created_key") for item in document["issues"]):
        raise ValueError("a Jira task is still marked posting; reconcile in Jira before retrying")
    endpoint = base.rstrip("/") + "/rest/api/2/issue"
    opener = urllib.request.build_opener(RefuseRedirects())
    for item in document["issues"]:
        if item.get("created_key"):
            continue
        item["posting"] = True
        persist(document, output)
        body = canonical_payload(item)
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
            with opener.open(request, timeout=15) as response:
                created = json.load(response)
        except urllib.error.HTTPError as exc:
            exc.close()
            if 300 <= exc.code < 400:
                raise ValueError(f"Jira write refused redirect (HTTP {exc.code})") from None
            raise ValueError(f"Jira returned HTTP {exc.code}; response body omitted") from None
        except urllib.error.URLError as exc:
            raise ValueError(f"Jira connection failed: {exc.reason}") from None
        key = created.get("key") if isinstance(created, dict) else None
        if not isinstance(key, str) or not key:
            raise ValueError("Jira response did not contain an issue key")
        item["created_key"] = key
        item["posted_payload_sha256"] = hashlib.sha256(body).hexdigest()
        item["posted_sha256"] = item["posted_payload_sha256"]
        item.pop("posting", None)
        persist(document, output)


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
        document = saved_state(document, output)
        csv_path = None
        if args.csv is not None:
            csv_path = (Path("outputs") / f"{slug}-jira-payload.csv") if args.csv is True else Path(args.csv)
        if args.apply:
            base = os.environ.get("JIRA_URL")
            token = os.environ.get("JIRA_TOKEN")
            if not base or not token:
                raise ValueError("--apply requires JIRA_URL and JIRA_TOKEN")
            if not safe_target(base):
                raise ValueError("refusing non-HTTPS Jira URL; plain HTTP is allowed only to 127.0.0.1")
            current_url = normalize_jira_url(base)
            stored_url = document.get("jira_url")
            if stored_url and normalize_jira_url(stored_url) != current_url:
                raise ValueError(f"state file belongs to {stored_url}; use a new --out or reconcile")
            if any(item.get("posting") and not item.get("created_key") for item in document["issues"]):
                raise ValueError("a Jira task is still marked posting; reconcile in Jira before retrying")
            pending = sum(not item.get("created_key") for item in document["issues"])
            print(f"Ready to create {pending} Jira issues.")
            if not args.yes:
                if input("Type yes to continue: ") != "yes":
                    print("Cancelled; no Jira issues were created.")
                    return 0
            document["jira_url"] = current_url
            persist(document, output)
            if csv_path is not None:
                write_csv(document, csv_path)
            write_issues(document, base, token, output)
            print(f"Created {pending} Jira issues; keys saved to {output}.")
            for note in stale_notes(document):
                print(note)
        else:
            persist(document, output)
            if csv_path is not None:
                write_csv(document, csv_path)
            print(f"Dry run: {len(document['issues'])} Jira issue payloads written to {output}.")
            for note in stale_notes(document):
                print(note)
            if csv_path is not None:
                print(f"CSV written to {csv_path}.")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"plan_to_tracker: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
