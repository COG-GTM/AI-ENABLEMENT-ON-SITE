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


def handle(msg: dict):
    """Return a response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return ok(mid, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "notifications/initialized" or (method or "").startswith("notifications/"):
        return None
    if method == "ping":
        return ok(mid, {})
    if method == "tools/list":
        return ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return err(mid, -32602, f"unknown tool: {name}")
        try:
            text = fn(params.get("arguments") or {})
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
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            out.write(json.dumps(err(None, -32700, "parse error")) + "\n")
            out.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()


if __name__ == "__main__":
    serve(sys.stdin, sys.stdout)
