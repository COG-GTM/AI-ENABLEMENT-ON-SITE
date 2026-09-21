"""Drives server.py over a real stdio pipe. Run: python -m unittest integrations/reference-mcp/test_server.py"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"


def rpc(messages: list) -> list[dict]:
    stdin = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
    r = subprocess.run([sys.executable, str(SERVER)], input=stdin, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


class ReferenceServerTests(unittest.TestCase):
    def test_handshake_and_tool_list(self):
        out = rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual(len(out), 2)  # the notification gets no reply
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "reference-system")
        names = {t["name"] for t in out[1]["result"]["tools"]}
        self.assertEqual(names, {"tracker_summary", "get_requirement", "what_if_power"})

    def test_every_tool_runs(self):
        out = rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "tracker_summary", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_requirement", "arguments": {"id": "SN-REQ-006"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "what_if_power", "arguments": {"imu": "imu-b", "mcu_duty": 0.25}}},
        ])
        for o in out:
            self.assertFalse(o["result"]["isError"], o)
        summary = json.loads(out[0]["result"]["content"][0]["text"])
        self.assertIn("open", summary)
        req = json.loads(out[1]["result"]["content"][0]["text"])
        self.assertEqual(req["id"], "SN-REQ-006")
        self.assertIn("CRC", req["requirement"])
        self.assertIn("PASS", out[2]["result"]["content"][0]["text"])

    def test_bad_input_is_reported_not_crashed(self):
        out = rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_requirement", "arguments": {"id": "../../etc"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "what_if_power", "arguments": {"imu": "nope"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delete_everything"}},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
            "{not json",
            "[1, 2]",
        ])
        self.assertTrue(out[0]["result"]["isError"])
        self.assertTrue(out[1]["result"]["isError"])
        self.assertEqual(out[2]["error"]["code"], -32602)
        self.assertEqual(out[3]["error"]["code"], -32601)
        self.assertEqual(out[4]["error"]["code"], -32700)
        self.assertEqual(out[5]["error"]["code"], -32700)

    def test_malformed_params_and_arguments_get_invalid_params_error(self):
        out = rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": "get_requirement"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": 7},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_requirement", "arguments": ["SN-REQ-001"]}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_requirement", "arguments": "SN-REQ-001"}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": ["what_if_power"]}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "what_if_power", "arguments": {"mcu_duty": "0.5"}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "what_if_power", "arguments": {"mcu_duty": 1.5}}},
            {"jsonrpc": "2.0", "id": 9, "method": 5},
            {"jsonrpc": "2.0", "method": "notifications/progress", "params": [1]},
            {"jsonrpc": "2.0", "id": 10, "method": "ping"},
        ])
        self.assertEqual(len(out), 10)  # the notification gets no reply; the server is still alive for ping
        for i in range(6):
            self.assertEqual(out[i]["error"]["code"], -32602, out[i])
        self.assertTrue(out[6]["result"]["isError"])
        self.assertTrue(out[7]["result"]["isError"])
        self.assertEqual(out[8]["error"]["code"], -32600)
        self.assertEqual(out[9], {"jsonrpc": "2.0", "id": 10, "result": {}})


if __name__ == "__main__":
    unittest.main()
