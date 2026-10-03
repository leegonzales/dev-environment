"""Tests for proxy startup: per-server isolation and eager initialization."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import aiohttp
import pytest

import mcp_proxy.backend as backend_mod
from mcp_proxy.cli import start_all, stop_all
from mcp_proxy.config import ProxyConfig, ServerConfig
from tests.test_server import FAKE_SERVER

STALE_SESSION = "11111111-2222-3333-4444-555555555555"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fake_script(tmp_path: Path) -> Path:
    s = tmp_path / "fake.py"
    s.write_text(FAKE_SERVER)
    return s


async def _call(port: int, body: dict, session: str = STALE_SESSION) -> dict:
    async with aiohttp.ClientSession() as http, http.post(
        f"http://127.0.0.1:{port}/mcp",
        json=body,
        headers={"Mcp-Session-Id": session},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        return json.loads(await resp.text())


TOOL_CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "greet", "arguments": {"name": "proxy"}},
}


@pytest.mark.asyncio
async def test_bad_backend_does_not_stop_the_others(
    tmp_path: Path, fake_script: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend_mod, "READY_WAIT_MAX", 0.5)
    bad, good = _free_port(), _free_port()
    config = ProxyConfig(
        request_timeout=30,
        servers=[
            ServerConfig("bad", str(tmp_path / "no-such-binary"), [], {}, bad),
            ServerConfig("good", sys.executable, [str(fake_script)], {}, good),
        ],
    )
    pairs = await start_all(config)
    try:
        ok = await _call(good, TOOL_CALL)
        assert ok["result"]["content"][0]["text"] == "hi proxy"
        err = await _call(bad, TOOL_CALL)
        assert "error" in err
    finally:
        await stop_all(pairs)


@pytest.mark.asyncio
async def test_port_in_use_skips_only_that_server(fake_script: Path) -> None:
    taken, free = _free_port(), _free_port()
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", taken))
    blocker.listen()
    config = ProxyConfig(
        servers=[
            ServerConfig("clash", sys.executable, [str(fake_script)], {}, taken),
            ServerConfig("fine", sys.executable, [str(fake_script)], {}, free),
        ],
    )
    try:
        pairs = await start_all(config)
        try:
            ok = await _call(free, TOOL_CALL)
            assert ok["result"]["content"][0]["text"] == "hi proxy"
            assert [b.name for b, _ in pairs] == ["fine"]
        finally:
            await stop_all(pairs)
    finally:
        blocker.close()


@pytest.mark.asyncio
async def test_backends_are_initialized_eagerly(fake_script: Path) -> None:
    """After a proxy restart, connected clients keep their old session ids and
    never re-send initialize. The proxy must handshake each child itself, so
    servers that enforce initialize-before-call keep working."""
    port = _free_port()
    config = ProxyConfig(
        servers=[ServerConfig("warm", sys.executable, [str(fake_script)], {}, port)]
    )
    pairs = await start_all(config)
    try:
        backend = pairs[0][0]
        for _ in range(50):
            if backend._initialized:
                break
            await asyncio.sleep(0.1)
        assert backend._initialized, "proxy did not initialize the backend itself"
    finally:
        await stop_all(pairs)
