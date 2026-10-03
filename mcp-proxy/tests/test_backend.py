"""Tests for StdioBackend using a fake MCP server (Python script)."""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

import mcp_proxy.backend as backend_mod
from mcp_proxy.backend import BackendUnavailable, StdioBackend

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
            elif name == "big":
                # One JSON-RPC line far larger than asyncio's 64 KiB default.
                respond({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"content": [{"type": "text", "text": "x" * args["size"]}]},
                })
            elif name == "stderr_flood":
                # One huge stderr line, then a normal reply.
                sys.stderr.write("E" * args["size"] + "\\n")
                sys.stderr.flush()
                respond({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"content": [{"type": "text", "text": "survived"}]},
                })
            elif name == "die":
                # Crash mid-request without replying.
                import os
                os._exit(1)
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


# ── Resilience: one bad response or crash must not take the backend down ──


@pytest.mark.asyncio
async def test_response_line_over_64k_is_delivered(backend: StdioBackend) -> None:
    """A single response line larger than 64 KiB must arrive intact."""
    await backend.initialize()
    size = 1_000_000
    r = await backend.send_request(
        "tools/call", {"name": "big", "arguments": {"size": size}}, timeout=10
    )
    assert len(r["result"]["content"][0]["text"]) == size


@pytest.mark.asyncio
async def test_backend_still_serves_after_large_response(backend: StdioBackend) -> None:
    await backend.initialize()
    await backend.send_request(
        "tools/call", {"name": "big", "arguments": {"size": 500_000}}, timeout=10
    )
    r = await backend.send_request(
        "tools/call", {"name": "echo", "arguments": {"text": "after"}}, timeout=5
    )
    assert r["result"]["content"][0]["text"] == "after"


@pytest.mark.asyncio
async def test_huge_stderr_line_does_not_hang(backend: StdioBackend) -> None:
    await backend.initialize()
    r = await backend.send_request(
        "tools/call",
        {"name": "stderr_flood", "arguments": {"size": 1_000_000}},
        timeout=10,
    )
    assert r["result"]["content"][0]["text"] == "survived"
    r = await backend.send_request(
        "tools/call", {"name": "echo", "arguments": {"text": "ok"}}, timeout=5
    )
    assert r["result"]["content"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_child_exit_fails_pending_request_fast(backend: StdioBackend) -> None:
    """A crash mid-request must fail the caller now, not after the timeout."""
    await backend.initialize()
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    with pytest.raises(BackendUnavailable):
        await backend.send_request(
            "tools/call", {"name": "die", "arguments": {}}, timeout=30
        )
    assert loop.time() - t0 < 5


@pytest.mark.asyncio
async def test_backend_respawns_after_child_exit(backend: StdioBackend) -> None:
    """After the child dies, the next request is served by a fresh child."""
    await backend.initialize()
    first_pid = backend._process.pid
    with pytest.raises(BackendUnavailable):
        await backend.send_request(
            "tools/call", {"name": "die", "arguments": {}}, timeout=30
        )
    r = await backend.send_request(
        "tools/call", {"name": "echo", "arguments": {"text": "reborn"}}, timeout=15
    )
    assert r["result"]["content"][0]["text"] == "reborn"
    assert backend._process.pid != first_pid
    assert backend.is_running


# ── Startup isolation: a backend that cannot launch must not raise ──


@pytest.mark.asyncio
async def test_start_with_missing_command_does_not_raise(tmp_path: Path) -> None:
    b = StdioBackend("ghost", str(tmp_path / "no-such-binary"), [])
    await b.start()  # must not raise: one bad server cannot kill the proxy
    try:
        assert not b.is_running
    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_request_to_unstartable_backend_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A down backend fails a request within the ready-wait cap, not the
    caller's (much longer) timeout."""
    monkeypatch.setattr(backend_mod, "READY_WAIT_MAX", 0.5)
    b = StdioBackend("ghost", str(tmp_path / "no-such-binary"), [])
    await b.start()
    try:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        with pytest.raises(BackendUnavailable):
            await b.send_request("tools/list", timeout=30)
        assert loop.time() - t0 < 3
    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_backend_recovers_once_command_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Started before its binary exists, the backend keeps retrying and serves
    once the binary appears (e.g. an npx cache that was still installing)."""
    monkeypatch.setattr(backend_mod, "RESPAWN_BASE_DELAY", 0.05)
    monkeypatch.setattr(backend_mod, "RESPAWN_MAX_DELAY", 0.2)
    exe = tmp_path / "late-server"
    b = StdioBackend("late", str(exe), [])
    await b.start()
    try:
        assert not b.is_running
        exe.write_text(f"#!{sys.executable}\n" + FAKE_SERVER)
        exe.chmod(0o755)
        r = await b.send_request(
            "tools/call", {"name": "echo", "arguments": {"text": "late"}}, timeout=10
        )
        assert r["result"]["content"][0]["text"] == "late"
        assert b.is_running
    finally:
        await b.stop()


FLAKY_INIT_SERVER = textwrap.dedent("""\
    import json, sys

    calls = 0
    for line in sys.stdin:
        req = json.loads(line)
        rid = req.get("id")
        if rid is None:
            continue
        if req.get("method") == "initialize":
            calls += 1
            if calls == 1:
                out = {"jsonrpc": "2.0", "id": rid,
                       "error": {"code": -32603, "message": "warming up"}}
            else:
                out = {"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "serverInfo": {"name": "flaky", "version": "1"}}}
            sys.stdout.write(json.dumps(out) + "\\n")
            sys.stdout.flush()
""")


@pytest.mark.asyncio
async def test_failed_initialize_is_not_cached(tmp_path: Path) -> None:
    """An error reply to initialize must not be cached for every later client.

    The proxy initializes eagerly at startup, so a transient startup error
    would otherwise be served to all sessions forever.
    """
    script = tmp_path / "flaky.py"
    script.write_text(FLAKY_INIT_SERVER)
    b = StdioBackend("flaky", sys.executable, [str(script)])
    await b.start()
    try:
        with pytest.raises(BackendUnavailable):
            await b.initialize()
        assert not b._initialized
        r = await b.initialize()
        assert r["result"]["serverInfo"]["name"] == "flaky"
        assert (await b.initialize()) is r  # the good result is what gets cached
    finally:
        await b.stop()
