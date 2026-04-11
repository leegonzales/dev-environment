#!/usr/bin/env python3
"""Smoke test — start proxy with a single real-ish server and hit it via HTTP.

Usage:
    uv run python tests/smoke_test.py

This starts the proxy with a minimal config, sends the full MCP lifecycle
(initialize → initialized → tools/list → tools/call), and prints results.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import textwrap
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp

from mcp_proxy.backend import StdioBackend
from mcp_proxy.server import McpHttpServer

FAKE_SERVER = textwrap.dedent("""\
    import json, sys, time

    def respond(msg):
        sys.stdout.write(json.dumps(msg, separators=(",", ":")) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        rid = req.get("id")
        method = req.get("method", "")
        if rid is None:
            continue
        if method == "initialize":
            respond({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "smoke-test-server", "version": "1.0.0"},
            }})
        elif method == "tools/list":
            respond({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": "get_time", "description": "Returns current time", "inputSchema": {"type": "object"}},
                {"name": "echo", "description": "Echoes text", "inputSchema": {
                    "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            ]}})
        elif method == "tools/call":
            name = req.get("params", {}).get("name")
            args = req.get("params", {}).get("arguments", {})
            if name == "get_time":
                respond({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"time={time.time():.0f}"}]}})
            elif name == "echo":
                respond({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": args.get("text", "")}]}})
            else:
                respond({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"no tool: {name}"}})
        else:
            respond({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown: {method}"}})
""")

PORT = 19999


async def smoke() -> bool:
    # Write fake server script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(FAKE_SERVER)
        script = f.name

    backend = StdioBackend("smoke", sys.executable, [script])
    server = McpHttpServer(backend, "127.0.0.1", PORT)

    await backend.start()
    await server.start()

    url = f"http://127.0.0.1:{PORT}/mcp"
    ok = True

    try:
        async with aiohttp.ClientSession() as session:
            # Health check
            async with session.get(f"http://127.0.0.1:{PORT}/health") as r:
                health = await r.json()
                print(f"  health: {health['status']} (PID {health['pid']})")

            # Simulate 3 concurrent clients
            for client_num in range(1, 4):
                print(f"\n  --- Client {client_num} ---")

                # Initialize
                async with session.post(url, json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": f"client-{client_num}", "version": "1.0"},
                    },
                }, headers={"Accept": "application/json, text/event-stream"}) as r:
                    data = await r.json()
                    sid = r.headers.get("Mcp-Session-Id", "none")
                    print(f"  init: {data['result']['serverInfo']['name']} (session={sid[:8]}...)")

                # Notification
                async with session.post(url, json={
                    "jsonrpc": "2.0", "method": "notifications/initialized",
                }, headers={"Mcp-Session-Id": sid, "Accept": "application/json, text/event-stream"}) as r:
                    print(f"  notifications/initialized: {r.status}")

                # tools/list
                async with session.post(url, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list",
                }, headers={"Mcp-Session-Id": sid, "Accept": "application/json, text/event-stream"}) as r:
                    data = await r.json()
                    tools = [t["name"] for t in data["result"]["tools"]]
                    print(f"  tools/list: {tools}")

                # tools/call
                async with session.post(url, json={
                    "jsonrpc": "2.0", "id": 3,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": f"hello from client {client_num}"}},
                }, headers={"Mcp-Session-Id": sid, "Accept": "application/json, text/event-stream"}) as r:
                    data = await r.json()
                    text = data["result"]["content"][0]["text"]
                    print(f"  echo: {text}")
                    if text != f"hello from client {client_num}":
                        print(f"  FAIL: expected 'hello from client {client_num}'")
                        ok = False

    except Exception as e:
        print(f"  ERROR: {e}")
        ok = False
    finally:
        await server.stop()
        await backend.stop()
        Path(script).unlink(missing_ok=True)

    return ok


def main() -> None:
    print("\nmcp-proxy-mux smoke test\n")
    success = asyncio.run(smoke())
    print(f"\n  {'PASS' if success else 'FAIL'}\n")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
