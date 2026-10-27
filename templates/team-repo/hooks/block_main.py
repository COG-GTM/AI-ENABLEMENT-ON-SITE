#!/usr/bin/env python3
"""Block Devin exec requests that commit on or push to main/master."""

import json
import shlex
import subprocess
import sys

PROTECTED = {"main", "master"}
OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def command_text(event: dict) -> str:
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command", "")
    return command if isinstance(command, str) else ""


def git_operations(command: str) -> list[tuple[str, list[str]]]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    operations = []
    for start, token in enumerate(tokens):
        if token != "git":
            continue
        index = start + 1
        while index < len(tokens):
            value = tokens[index]
            if value in {"commit", "push"}:
                operations.append((value, tokens[index + 1:]))
                break
            if value in OPTIONS_WITH_VALUE:
                index += 2
            elif value.startswith("-"):
                index += 1
            else:
                break
    return operations


def current_branch(cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def push_targets_protected(args: list[str], branch: str) -> bool:
    refs = []
    index = 0
    while index < len(args):
        value = args[index]
        if value in {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--force-if-includes"}:
            index += 2
            continue
        if value.startswith("-"):
            if value in {"--all", "--mirror"}:
                return True
            index += 1
            continue
        refs.append(value)
        index += 1
    if not refs or len(refs) == 1:
        return branch in PROTECTED
    refspecs = refs[1:]
    for refspec in refspecs:
        target = refspec.rsplit(":", 1)[-1]
        target = target.split("@", 1)[0].removeprefix("refs/heads/")
        if target in PROTECTED:
            return True
    return False


def evaluate(event: dict) -> bool:
    if event.get("tool_name") != "exec":
        return False
    tool_input = event.get("tool_input", {})
    cwd = tool_input.get("cwd") if isinstance(tool_input, dict) and isinstance(tool_input.get("cwd"), str) else None
    branch = current_branch(cwd)
    for operation, args in git_operations(command_text(event)):
        if operation == "commit" and branch in PROTECTED:
            return True
        if operation == "push" and push_targets_protected(args, branch):
            return True
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(event, dict) or not evaluate(event):
        return 0
    print("Blocked: do not commit on or push to main/master; use a feature branch.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
