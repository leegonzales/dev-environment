"""Tests for StdioBackend using a fake MCP server (Python script)."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest

from mcp_proxy.backend import StdioBackend

# A minimal fake MCP server that responds to JSON-RPC on stdin/stdout
FAKE_SERVER = textwrap.dedent("""\
    import json, sys

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
            # notification — ignore
            continue

        if method == "initialize":
            respond({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-server", "version": "0.0.1"},
                },
            })
        elif method == "tools/list":
            respond({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "echoes input",
                            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                        }
                    ]
                },
            })
        elif method == "tools/call":
            name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {})
            if name == "echo":
                respond({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"content": [{"type": "text", "text": args.get("text", "")}]},
                })
            else:
                respond({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"},
                })
        else:
            respond({
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            })
""")


@pytest.fixture
def fake_server_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_mcp.py"
    script.write_text(FAKE_SERVER)
    return script


@pytest.fixture
async def backend(fake_server_script: Path) -> StdioBackend:
    b = StdioBackend(
        name="test",
        command=sys.executable,
        args=[str(fake_server_script)],
    )
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
async def test_initialize(backend: StdioBackend) -> None:
    result = await backend.initialize()
    assert result["result"]["serverInfo"]["name"] == "fake-server"
    assert backend._initialized is True


@pytest.mark.asyncio
async def test_initialize_cached(backend: StdioBackend) -> None:
    r1 = await backend.initialize()
    r2 = await backend.initialize()
    assert r1 is r2  # exact same object — cached


@pytest.mark.asyncio
async def test_tools_list(backend: StdioBackend) -> None:
    await backend.initialize()
    result = await backend.send_request("tools/list")
    tools = result["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"


@pytest.mark.asyncio
async def test_tool_call(backend: StdioBackend) -> None:
    await backend.initialize()
    result = await backend.send_request(
        "tools/call",
        {"name": "echo", "arguments": {"text": "hello proxy"}},
    )
    assert result["result"]["content"][0]["text"] == "hello proxy"


@pytest.mark.asyncio
async def test_concurrent_requests(backend: StdioBackend) -> None:
    """Multiple requests in flight should all get correct responses."""
    await backend.initialize()

    async def call(text: str) -> str:
        r = await backend.send_request(
            "tools/call", {"name": "echo", "arguments": {"text": text}}
        )
        return r["result"]["content"][0]["text"]

    results = await asyncio.gather(
        call("a"), call("b"), call("c"), call("d"), call("e"),
    )
    assert results == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_id_remapping_no_collision(backend: StdioBackend) -> None:
    """Each request gets a unique upstream ID — no collisions."""
    await backend.initialize()
    ids_seen: set[int] = set()
    for _ in range(20):
        uid = backend._alloc_id()
        assert uid not in ids_seen
        ids_seen.add(uid)


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(backend: StdioBackend) -> None:
    await backend.initialize()
    result = await backend.send_request(
        "tools/call", {"name": "nonexistent", "arguments": {}}
    )
    assert "error" in result
    assert result["error"]["code"] == -32601
