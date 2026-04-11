"""Integration tests — HTTP server + stdio backend with fake MCP server."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import aiohttp
import pytest

from mcp_proxy.backend import StdioBackend
from mcp_proxy.server import McpHttpServer

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
                "result": {"tools": [{"name": "greet", "description": "says hi", "inputSchema": {"type": "object"}}]},
            })
        elif method == "tools/call":
            args = req.get("params", {}).get("arguments", {})
            respond({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": f"hi {args.get('name', 'world')}"}]},
            })
        else:
            respond({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown: {method}"}})
""")

TEST_PORT = 19876


@pytest.fixture
def fake_script(tmp_path: Path) -> Path:
    s = tmp_path / "fake.py"
    s.write_text(FAKE_SERVER)
    return s


@pytest.fixture
async def proxy_url(fake_script: Path):
    backend = StdioBackend("test", sys.executable, [str(fake_script)])
    server = McpHttpServer(backend, "127.0.0.1", TEST_PORT)
    await backend.start()
    await server.start()
    yield f"http://127.0.0.1:{TEST_PORT}/mcp"
    await server.stop()
    await backend.stop()


@pytest.mark.asyncio
async def test_health(fake_script: Path) -> None:
    backend = StdioBackend("test", sys.executable, [str(fake_script)])
    server = McpHttpServer(backend, "127.0.0.1", TEST_PORT + 1)
    await backend.start()
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{TEST_PORT + 1}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ok"
                assert data["server"] == "test"
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_initialize_via_http(proxy_url: str) -> None:
    async with aiohttp.ClientSession() as session:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        async with session.post(
            proxy_url,
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["id"] == 1
            assert data["result"]["serverInfo"]["name"] == "fake-server"
            assert "Mcp-Session-Id" in resp.headers


@pytest.mark.asyncio
async def test_full_lifecycle(proxy_url: str) -> None:
    """Initialize → notifications/initialized → tools/list → tools/call."""
    async with aiohttp.ClientSession() as session:
        # 1. Initialize
        init_resp = await session.post(
            proxy_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert init_resp.status == 200
        session_id = init_resp.headers["Mcp-Session-Id"]

        # 2. Initialized notification
        notif_resp = await session.post(
            proxy_url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "application/json, text/event-stream",
            },
        )
        assert notif_resp.status == 202

        # 3. tools/list
        list_resp = await session.post(
            proxy_url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "application/json, text/event-stream",
            },
        )
        assert list_resp.status == 200
        list_data = await list_resp.json()
        assert list_data["id"] == 2
        assert list_data["result"]["tools"][0]["name"] == "greet"

        # 4. tools/call
        call_resp = await session.post(
            proxy_url,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "greet", "arguments": {"name": "Lee"}},
            },
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "application/json, text/event-stream",
            },
        )
        assert call_resp.status == 200
        call_data = await call_resp.json()
        assert call_data["id"] == 3
        assert call_data["result"]["content"][0]["text"] == "hi Lee"


@pytest.mark.asyncio
async def test_multiple_clients_share_backend(proxy_url: str) -> None:
    """Two independent clients both get correct responses."""
    async with aiohttp.ClientSession() as s1, aiohttp.ClientSession() as s2:
        # Both initialize
        for client, cid in [(s1, 10), (s2, 20)]:
            resp = await client.post(
                proxy_url,
                json={
                    "jsonrpc": "2.0",
                    "id": cid,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": f"client-{cid}", "version": "1.0"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["id"] == cid  # ID correctly remapped per client

        # Both call tools concurrently
        import asyncio

        async def call(client: aiohttp.ClientSession, name: str, req_id: int) -> str:
            resp = await client.post(
                proxy_url,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": "tools/call",
                    "params": {"name": "greet", "arguments": {"name": name}},
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            data = await resp.json()
            assert data["id"] == req_id
            return data["result"]["content"][0]["text"]

        r1, r2 = await asyncio.gather(
            call(s1, "Alice", 11),
            call(s2, "Bob", 21),
        )
        assert r1 == "hi Alice"
        assert r2 == "hi Bob"


@pytest.mark.asyncio
async def test_delete_session(proxy_url: str) -> None:
    async with aiohttp.ClientSession() as session:
        # Initialize to get session
        resp = await session.post(
            proxy_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        sid = resp.headers["Mcp-Session-Id"]

        # Delete
        del_resp = await session.delete(
            proxy_url,
            headers={"Mcp-Session-Id": sid},
        )
        assert del_resp.status == 200


@pytest.mark.asyncio
async def test_bad_content_type(proxy_url: str) -> None:
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            proxy_url,
            data="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status == 415


@pytest.mark.asyncio
async def test_batch_request(proxy_url: str) -> None:
    """JSON-RPC batch with init + tool call."""
    async with aiohttp.ClientSession() as session:
        # First initialize standalone (needed before other calls)
        await session.post(
            proxy_url,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )

        # Now batch two tool calls
        batch = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "greet", "arguments": {"name": "batch"}},
            },
        ]
        resp = await session.post(
            proxy_url,
            json=batch,
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
