"""HTTP-level tests for token auth and the Host check (fake stdio backend)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import aiohttp
import pytest

from mcp_proxy.auth import Authenticator, TokenStore
from mcp_proxy.backend import StdioBackend
from mcp_proxy.server import McpHttpServer

from .test_server import FAKE_SERVER

TOKEN = "s" * 32
PORT = 20100  # each test takes its own port


def init_body() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    }


def list_body() -> dict:
    return {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    p = tmp_path / "token"
    p.write_text(TOKEN + "\n")
    os.chmod(p, 0o600)
    return p


async def run_server(tmp_path: Path, mode: str | None, port: int, token_file: Path):
    script = tmp_path / "fake.py"
    script.write_text(FAKE_SERVER)
    backend = StdioBackend("test", sys.executable, [str(script)])
    auth = (
        None
        if mode is None
        else Authenticator(mode, TokenStore(token_file), port=port, name="test")
    )
    server = McpHttpServer(backend, "127.0.0.1", port, auth=auth)
    await backend.start()
    await server.start()
    return backend, server, auth


async def post(port: int, body: dict, headers: dict | None = None, host=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if host:
        h["Host"] = host
    async with aiohttp.ClientSession() as s:
        async with s.post(f"http://127.0.0.1:{port}/mcp", json=body, headers=h) as r:
            return r.status, await r.text()


# ── enforce ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_rejects_missing_wrong_and_malformed(tmp_path, token_file):
    port = PORT + 1
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        for headers in (
            {},
            {"Authorization": "Bearer wrong-token-wrong-token-00"},
            {"Authorization": "Basic " + TOKEN},
            {"Authorization": "Bearer "},
            {"Authorization": "Bearer ${MCP_PROXY_TOKEN}"},
        ):
            status, text = await post(port, list_body(), headers)
            assert status == 401, headers
            assert TOKEN not in text
            assert "restart" in text.lower() or "reconnect" in text.lower()
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_enforce_accepts_right_token(tmp_path, token_file):
    port = PORT + 2
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        h = {"Authorization": f"Bearer {TOKEN}"}
        status, _ = await post(port, init_body(), h)
        assert status == 200
        status, text = await post(port, list_body(), h)
        assert status == 200 and "greet" in text
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_enforce_rejects_foreign_host_even_with_token(tmp_path, token_file):
    port = PORT + 3
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        h = {"Authorization": f"Bearer {TOKEN}"}
        status, _ = await post(port, list_body(), h, host="evil.example:%d" % port)
        assert status == 421
        status, _ = await post(port, list_body(), h, host=f"localhost:{port}")
        assert status == 200
        status, _ = await post(port, list_body(), h, host=f"127.0.0.1:{port}")
        assert status == 200
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_enforce_applies_to_get_and_delete(tmp_path, token_file):
    port = PORT + 4
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{port}/mcp") as r:
                assert r.status == 401
            async with s.delete(f"http://127.0.0.1:{port}/mcp") as r:
                assert r.status == 401
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_enforce_health_is_redacted_without_token(tmp_path, token_file):
    port = PORT + 5
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{port}/health") as r:
                assert r.status == 200
                data = await r.json()
            assert data["status"] == "ok" and data["auth"] == "enforce"
            assert "pid" not in data and "sessions" not in data
            assert "unauth" not in data

            async with s.get(
                f"http://127.0.0.1:{port}/health",
                headers={"Authorization": f"Bearer {TOKEN}"},
            ) as r:
                full = await r.json()
            assert full["pid"] and "sessions" in full and full["unauth"] == 0
    finally:
        await server.stop()
        await backend.stop()


# ── audit ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_lets_everything_through_and_counts(tmp_path, token_file):
    port = PORT + 6
    backend, server, auth = await run_server(tmp_path, "audit", port, token_file)
    try:
        status, _ = await post(port, list_body())  # no header
        assert status == 200
        status, _ = await post(
            port, list_body(), {"Authorization": "Bearer ${MCP_PROXY_TOKEN}"}
        )
        assert status == 200
        status, _ = await post(
            port, list_body(), {"Authorization": f"Bearer {TOKEN}"}
        )
        assert status == 200
        status, _ = await post(port, list_body(), host=f"evil.example:{port}")
        assert status == 200

        snap = auth.snapshot()
        # no header (x2: the first and the foreign-host one) and one bad template
        assert snap["unauth_absent"] == 2
        assert snap["unauth_invalid"] == 1
        assert snap["unauth"] == 3
        assert snap["bad_host"] == 1
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_audit_health_is_full_and_not_counted(tmp_path, token_file):
    port = PORT + 7
    backend, server, auth = await run_server(tmp_path, "audit", port, token_file)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{port}/health") as r:
                data = await r.json()
        assert data["pid"] and data["auth"] == "audit" and data["unauth"] == 0
        assert auth.snapshot()["unauth"] == 0
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_audit_without_a_token_file_still_serves(tmp_path):
    port = PORT + 8
    missing = tmp_path / "no-such-token"
    backend, server, auth = await run_server(tmp_path, "audit", port, missing)
    try:
        status, _ = await post(port, list_body(), {"Authorization": "Bearer abc"})
        assert status == 200
        assert auth.snapshot()["unauth_invalid"] == 1
    finally:
        await server.stop()
        await backend.stop()


# ── off / no auth object ─────────────────────────────────


@pytest.mark.asyncio
async def test_no_auth_object_behaves_as_before(tmp_path, token_file):
    port = PORT + 9
    backend, server, auth = await run_server(tmp_path, None, port, token_file)
    try:
        status, _ = await post(port, list_body())
        assert status == 200
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{port}/health") as r:
                data = await r.json()
        assert data["pid"] and "auth" not in data
    finally:
        await server.stop()
        await backend.stop()


@pytest.mark.asyncio
async def test_off_mode_does_not_count(tmp_path, token_file):
    port = PORT + 10
    backend, server, auth = await run_server(tmp_path, "off", port, token_file)
    try:
        status, _ = await post(port, list_body(), host=f"evil.example:{port}")
        assert status == 200
        assert auth.snapshot()["unauth"] == 0 and auth.snapshot()["bad_host"] == 0
    finally:
        await server.stop()
        await backend.stop()


# ── logs never hold the token ────────────────────────────


@pytest.mark.asyncio
async def test_logs_never_hold_a_token(tmp_path, token_file, caplog):
    caplog.set_level("DEBUG")
    port = PORT + 11
    backend, server, auth = await run_server(tmp_path, "enforce", port, token_file)
    try:
        await post(port, list_body(), {"Authorization": "Bearer leaked-value-123456789012"})
        await post(port, list_body(), {"Authorization": f"Bearer {TOKEN}"})
    finally:
        await server.stop()
        await backend.stop()
    assert TOKEN not in caplog.text
    assert "leaked-value" not in caplog.text
