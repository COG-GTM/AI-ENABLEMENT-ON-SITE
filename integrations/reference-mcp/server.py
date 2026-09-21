#!/usr/bin/env python3
"""A complete, read-only MCP server in one file. Standard library only, stdio transport.

It exposes three tools over the synthetic system in example-system/:
  tracker_summary     -> open/closed counts and top open items (tools/tracker_report.py)
  get_requirement     -> one requirement row from docs/SRS.md by id (e.g. SN-REQ-006)
  what_if_power       -> power budget for a part swap (tools/what_if.py)

Run by hand to see the wire protocol:
    python integrations/reference-mcp/server.py < integrations/reference-mcp/handshake.jsonl

Wire it into Devin: copy the "reference-system" entry from integrations/mcp_config.example.json into
.devin/mcp_config.json. Devin starts this process and talks JSON-RPC 2.0, one message per line.

Protocol subset implemented: initialize, notifications/initialized, ping, tools/list, tools/call.
Everything else returns JSON-RPC error -32601 (method not found). No network, no writes.
"""

import io
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "example-system"
PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "reference-system", "version": "1.0.0"}
REQ_ID_RE = re.compile(r"^SN-REQ-\d{3}$")
PART_RE = re.compile(r"^[a-z0-9-]{1,32}$")

TOOLS = [
    {
        "name": "tracker_summary",
        "description": "Summarise example-system/tracker.json: totals, open by severity and component, top open items.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_requirement",
        "description": "Return one requirement from example-system/docs/SRS.md by id, e.g. SN-REQ-006.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "pattern": "^SN-REQ-[0-9]{3}$"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "what_if_power",
        "description": "Recompute the power budget with a different IMU and/or uplink part (ids from example-system/parts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "imu": {"type": "string", "pattern": "^[a-z0-9-]{1,32}$"},
                "uplink": {"type": "string", "pattern": "^[a-z0-9-]{1,32}$"},
                "mcu_duty": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "additionalProperties": False,
        },
    },
]


def schema_errors(schema: dict, value: dict) -> list[str]:
    """Check `value` against the small JSON Schema subset used in TOOLS (object with typed properties)."""
    errs = []
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value:
            errs.append(f"missing required argument: {key}")
    if schema.get("additionalProperties") is False:
        errs += [f"unexpected argument: {k}" for k in value if k not in props]
    for key, rule in props.items():
        if key not in value:
            continue
        v = value[key]
        if rule["type"] == "string":
            if not isinstance(v, str):
                errs.append(f"{key} must be a string")
            elif "pattern" in rule and not re.match(rule["pattern"], v):
                errs.append(f"{key} must match {rule['pattern']}")
        elif rule["type"] == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
                errs.append(f"{key} must be a finite number")
            elif v < rule.get("minimum", float("-inf")) or v > rule.get("maximum", float("inf")):
                errs.append(f"{key} must be between {rule.get('minimum')} and {rule.get('maximum')}")
    return errs


def reject_constant(token: str):
    raise ValueError(f"{token} is not valid JSON")


def run_tool(cmd: list[str]) -> str:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    if r.returncode not in (0, 2):
        raise ValueError("tool failed")
    return r.stdout


def tool_tracker_summary(_: dict) -> str:
    return run_tool([sys.executable, "tools/tracker_report.py", "--json"])


def tool_get_requirement(a: dict) -> str:
    rid = str(a.get("id", ""))
    if not REQ_ID_RE.match(rid):
        raise ValueError("id must look like SN-REQ-001")
    for line in (EXAMPLE / "docs" / "SRS.md").read_text().splitlines():
        if line.startswith(f"| {rid} "):
            cells = [c.strip() for c in line.strip("|").split("|")]
            keys = ("id", "requirement", "priority", "verified_by")
            return json.dumps(dict(zip(keys, cells)))
    raise ValueError(f"{rid} not found")


def tool_what_if_power(a: dict) -> str:
    cmd = [sys.executable, "tools/what_if.py", "--markdown"]
    for key in ("imu", "uplink"):
        if key in a:
            v = str(a[key])
            if not PART_RE.match(v):
                raise ValueError(f"invalid {key}")
            cmd += [f"--{key}", v]
    if "mcu_duty" in a:
        if isinstance(a["mcu_duty"], bool) or not isinstance(a["mcu_duty"], (int, float)):
            raise ValueError("mcu_duty must be a number")
        d = float(a["mcu_duty"])
        if not 0 <= d <= 1:
            raise ValueError("mcu_duty must be 0..1")
        cmd += ["--mcu-duty", str(d)]
    return run_tool(cmd)


HANDLERS = {
    "tracker_summary": tool_tracker_summary,
    "get_requirement": tool_get_requirement,
    "what_if_power": tool_what_if_power,
}
SCHEMAS = {t["name"]: t["inputSchema"] for t in TOOLS}


def handle(msg: dict):
    """Return a response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")
    if not isinstance(method, str):
        return err(mid, -32600, "method must be a string")
    if method.startswith("notifications/"):
        return None
    params = msg.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return err(mid, -32602, "params must be an object")

    if method == "initialize":
        return ok(mid, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return ok(mid, {})
    if method == "tools/list":
        return ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name) if isinstance(name, str) else None
        if fn is None:
            return err(mid, -32602, f"unknown tool: {name}")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return err(mid, -32602, "arguments must be an object")
        bad = schema_errors(SCHEMAS[name], arguments)
        if bad:
            return err(mid, -32602, "; ".join(bad))
        try:
            text = fn(arguments)
            return ok(mid, {"content": [{"type": "text", "text": text}], "isError": False})
        except (ValueError, KeyError, subprocess.TimeoutExpired, OSError) as e:
            return ok(mid, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
    return err(mid, -32601, f"method not found: {method}")


def ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(inp: io.TextIOBase, out: io.TextIOBase) -> None:
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line, parse_constant=reject_constant)  # NaN/Infinity are not JSON
            if not isinstance(msg, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            out.write(json.dumps(err(None, -32700, "parse error")) + "\n")
            out.flush()
            continue
        try:
            resp = handle(msg)
        except Exception as e:  # one bad request must never take the whole server down
            resp = err(msg.get("id"), -32603, f"internal error: {type(e).__name__}")
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()


if __name__ == "__main__":
    serve(sys.stdin, sys.stdout)
