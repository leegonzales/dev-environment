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


# ── auth wiring ──────────────────────────────────────────

import os  # noqa: E402

from mcp_proxy.cli import auth_problems, build_authenticators  # noqa: E402


def _tok(path: Path, value: str = "k" * 32, mode: int = 0o600) -> Path:
    path.write_text(value + "\n")
    os.chmod(path, mode)
    return path


def test_enforce_with_missing_token_is_refused(tmp_path: Path) -> None:
    config = ProxyConfig(
        auth="enforce",
        token_file=tmp_path / "none",
        servers=[ServerConfig(name="a", command="cat", port=1)],
    )
    problems = auth_problems(config)
    assert problems and "a" in problems[0] and "missing" in problems[0]


def test_enforce_with_loose_token_is_refused(tmp_path: Path) -> None:
    config = ProxyConfig(
        auth="enforce",
        token_file=_tok(tmp_path / "tok", mode=0o644),
        servers=[ServerConfig(name="a", command="cat", port=1)],
    )
    assert auth_problems(config)


def test_audit_and_off_start_without_a_token(tmp_path: Path) -> None:
    for mode in ("audit", "off"):
        config = ProxyConfig(
            auth=mode,
            token_file=tmp_path / "none",
            servers=[ServerConfig(name="a", command="cat", port=1)],
        )
        assert auth_problems(config) == []


def test_per_server_enforce_is_checked_even_if_default_is_audit(tmp_path: Path) -> None:
    config = ProxyConfig(
        auth="audit",
        token_file=tmp_path / "none",
        servers=[ServerConfig(name="a", command="cat", port=1, auth="enforce")],
    )
    assert auth_problems(config)


def test_build_authenticators_one_per_server(tmp_path: Path) -> None:
    config = ProxyConfig(
        token_file=_tok(tmp_path / "tok"),
        servers=[
            ServerConfig(name="a", command="cat", port=1),
            ServerConfig(name="b", command="cat", port=2, auth="enforce"),
        ],
    )
    auths = build_authenticators(config)
    assert auths["a"].mode == "audit" and auths["b"].mode == "enforce"
    assert auths["a"].snapshot()["unauth"] == 0


@pytest.mark.asyncio
async def test_status_sends_the_token_and_shows_counts(tmp_path: Path, fake_script: Path, capsys) -> None:
    from mcp_proxy.cli import check_status

    port = _free_port()
    config = ProxyConfig(
        auth="enforce",
        token_file=_tok(tmp_path / "tok"),
        servers=[ServerConfig(name="fake", command=sys.executable, args=[str(fake_script)], port=port)],
    )
    pairs = await start_all(config)
    try:
        await check_status(config)
    finally:
        await stop_all(pairs)
    out = capsys.readouterr().out
    assert "ok" in out and "auth=enforce" in out and "unauth=0" in out
    assert "PID" in out
    assert "k" * 32 not in out


def _run_main(monkeypatch, argv: list[str]) -> int:
    from mcp_proxy import cli

    async def must_not_run(config):
        raise AssertionError("run() was reached: the auth check did not stop main()")

    monkeypatch.setattr(cli, "run", must_not_run)
    monkeypatch.setattr(sys, "argv", ["mcp-proxy-mux", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def _config_file(tmp_path: Path, token: Path, marker: Path, extra: str = "") -> Path:
    spawn = tmp_path / "spawn.py"
    spawn.write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        f'[proxy]\nauth = "enforce"\ntoken_file = "{token}"\n\n'
        f'[servers.a]\ncommand = "{sys.executable}"\nargs = ["{spawn}"]\nport = {_free_port()}\n'
        + extra
    )
    return cfg


@pytest.mark.parametrize("mode", [None, 0o644])
def test_main_exits_2_and_spawns_nothing_when_enforce_has_no_usable_token(
    tmp_path: Path, monkeypatch, capsys, mode
) -> None:
    token = tmp_path / "tok"
    if mode is not None:
        _tok(token, mode=mode)
    marker = tmp_path / "marker"
    cfg = _config_file(tmp_path, token, marker)
    assert _run_main(monkeypatch, ["-c", str(cfg)]) == 2
    err = capsys.readouterr().err
    assert "auth=enforce" in err and "[a]" in err
    assert not marker.exists(), "a backend was spawned before the auth check"


def test_main_server_filter_only_checks_the_selected_server(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    marker = tmp_path / "marker"
    cfg = _config_file(
        tmp_path,
        tmp_path / "none",
        marker,
        extra=f'\n[servers.b]\ncommand = "cat"\nport = {_free_port()}\nauth = "off"\n',
    )
    # b does not enforce, so selecting it must not be refused for the missing token.
    from mcp_proxy import cli

    seen = {}

    async def fake_run(config):
        seen["servers"] = [s.name for s in config.servers]

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["mcp-proxy-mux", "-c", str(cfg), "--server", "b"])
    cli.main()
    assert seen["servers"] == ["b"]
