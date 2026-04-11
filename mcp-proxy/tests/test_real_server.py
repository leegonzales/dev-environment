"""Integration test with a real MCP server (nanobanana-mcp).

Skipped if the server binary is not available.
Run with: uv run pytest tests/test_real_server.py -v -s
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import pytest

from mcp_proxy.backend import StdioBackend
from mcp_proxy.server import McpHttpServer

NANOBANANA_PATH = Path(
    "/Users/leegonzales/Projects/leegonzales/MCPServers/nanobanana-mcp/dist/index.js"
)

TEST_PORT = 19877

needs_nanobanana = pytest.mark.skipif(
    not NANOBANANA_PATH.exists(),
    reason="nanobanana-mcp not installed",
)


@pytest.fixture
async def real_proxy():
    backend = StdioBackend("nanobanana-mcp", "node", [str(NANOBANANA_PATH)])
    server = McpHttpServer(backend, "127.0.0.1", TEST_PORT, request_timeout=30)
    await backend.start()
    await server.start()
    # Give the node process a moment to initialize
    await asyncio.sleep(1)
    yield f"http://127.0.0.1:{TEST_PORT}/mcp"
    await server.stop()
    await backend.stop()


@needs_nanobanana
@pytest.mark.asyncio
async def test_real_health(real_proxy: str) -> None:
    url = real_proxy.replace("/mcp", "/health")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            print(f"\n  health: {data}")


@needs_nanobanana
@pytest.mark.asyncio
async def test_real_initialize(real_proxy: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            real_proxy,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test-real", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "result" in data
            assert "serverInfo" in data["result"]
            print(f"\n  server: {data['result']['serverInfo']}")
            assert "Mcp-Session-Id" in resp.headers


@needs_nanobanana
@pytest.mark.asyncio
async def test_real_tools_list(real_proxy: str) -> None:
    async with aiohttp.ClientSession() as session:
        # Init first
        init_resp = await session.post(
            real_proxy,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test-real", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        sid = init_resp.headers["Mcp-Session-Id"]

        # tools/list
        async with session.post(
            real_proxy,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={
                "Mcp-Session-Id": sid,
                "Accept": "application/json, text/event-stream",
            },
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            tools = data["result"]["tools"]
            names = [t["name"] for t in tools]
            print(f"\n  {len(tools)} tools: {names}")
            assert len(tools) > 0


@needs_nanobanana
@pytest.mark.asyncio
async def test_real_two_clients(real_proxy: str) -> None:
    """Two clients share the same backend process."""
    async with aiohttp.ClientSession() as c1, aiohttp.ClientSession() as c2:
        sessions = []
        for client in [c1, c2]:
            resp = await client.post(
                real_proxy,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "multi-client", "version": "1.0"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert resp.status == 200
            sessions.append(resp.headers["Mcp-Session-Id"])

        # Different session IDs, same backend
        assert sessions[0] != sessions[1]
        print(f"\n  sessions: {sessions[0][:8]}..., {sessions[1][:8]}...")

        # Both can list tools
        for client, sid in [(c1, sessions[0]), (c2, sessions[1])]:
            resp = await client.post(
                real_proxy,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers={
                    "Mcp-Session-Id": sid,
                    "Accept": "application/json, text/event-stream",
                },
            )
            data = await resp.json()
            assert "result" in data
            assert len(data["result"]["tools"]) > 0
