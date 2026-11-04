"""Unit tests for the token store and the Authenticator (no network)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_proxy.auth import (
    MIN_TOKEN_LEN,
    PREV_GRACE_S,
    Authenticator,
    TokenStore,
    parse_bearer,
)

TOKEN = "t" * 32
OTHER = "o" * 32


def write_token(path: Path, value: str, mode: int = 0o600) -> None:
    path.write_text(value + "\n")
    os.chmod(path, mode)


# ── parse_bearer ─────────────────────────────────────────


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("Bearer   abc  ", "abc"),
        ("Basic abc", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_bearer(header: str | None, expected: str | None) -> None:
    assert parse_bearer(header) == expected


# ── TokenStore ───────────────────────────────────────────


def test_store_missing_file_is_a_problem(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token")
    assert "missing" in (store.problem() or "")
    assert not store.verify(TOKEN)


def test_store_group_readable_file_is_a_problem(tmp_path: Path) -> None:
    p = tmp_path / "token"
    write_token(p, TOKEN, 0o640)
    store = TokenStore(p)
    assert "mode" in (store.problem() or "")
    # A file with loose permissions is not trusted, even for a matching token.
    assert not store.verify(TOKEN)


def test_store_short_token_is_a_problem(tmp_path: Path) -> None:
    p = tmp_path / "token"
    write_token(p, "x" * (MIN_TOKEN_LEN - 1))
    assert "short" in (TokenStore(p).problem() or "")


def test_store_empty_file_never_matches_empty(tmp_path: Path) -> None:
    p = tmp_path / "token"
    write_token(p, "")
    store = TokenStore(p)
    assert store.problem() is not None
    assert not store.verify("")


def test_store_good_file_verifies(tmp_path: Path) -> None:
    p = tmp_path / "token"
    write_token(p, TOKEN)
    store = TokenStore(p)
    assert store.problem() is None
    assert store.verify(TOKEN)
    assert not store.verify(OTHER)
    assert not store.verify("")
    assert store.read_token() == TOKEN


def test_store_picks_up_a_new_token_without_restart(tmp_path: Path) -> None:
    p = tmp_path / "token"
    write_token(p, TOKEN)
    store = TokenStore(p)
    assert store.verify(TOKEN)
    write_token(p, OTHER)
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 5_000_000_000))
    assert store.verify(OTHER)
    assert not store.verify(TOKEN)


def test_store_prev_token_is_accepted_for_24h_only(tmp_path: Path) -> None:
    p = tmp_path / "token"
    prev = tmp_path / "token.prev"
    write_token(p, OTHER)
    write_token(prev, TOKEN)
    now = [prev.stat().st_mtime + 60]
    store = TokenStore(p, clock=lambda: now[0])
    assert store.verify(OTHER)
    assert store.verify(TOKEN)
    now[0] = prev.stat().st_mtime + PREV_GRACE_S + 1
    assert store.verify(OTHER)
    assert not store.verify(TOKEN)


def test_store_loose_prev_file_is_ignored(tmp_path: Path) -> None:
    p = tmp_path / "token"
    prev = tmp_path / "token.prev"
    write_token(p, OTHER)
    write_token(prev, TOKEN, 0o644)
    store = TokenStore(p, clock=lambda: prev.stat().st_mtime + 1)
    assert not store.verify(TOKEN)


def test_store_uses_compare_digest(tmp_path: Path, monkeypatch) -> None:
    import hmac

    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr("mcp_proxy.auth.hmac.compare_digest", spy)
    p = tmp_path / "token"
    write_token(p, TOKEN)
    TokenStore(p).verify(OTHER)
    assert calls, "token comparison must use hmac.compare_digest"


# ── Authenticator ────────────────────────────────────────


def make(tmp_path: Path, mode: str, port: int = 9100) -> Authenticator:
    p = tmp_path / "token"
    write_token(p, TOKEN)
    return Authenticator(mode, TokenStore(p), port=port, name="t")


def test_authenticator_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Authenticator("enforse", TokenStore(tmp_path / "x"), port=1, name="t")


def test_host_check(tmp_path: Path) -> None:
    a = make(tmp_path, "enforce", port=9100)
    assert a.host_ok("127.0.0.1:9100")
    assert a.host_ok("localhost:9100")
    assert a.host_ok("[::1]:9100")
    assert not a.host_ok("evil.example:9100")
    assert not a.host_ok("127.0.0.1:9101")
    assert not a.host_ok("127.0.0.1")
    assert not a.host_ok(None)


def test_check_classifies(tmp_path: Path) -> None:
    a = make(tmp_path, "audit")
    assert a.check(f"Bearer {TOKEN}") == "ok"
    assert a.check(None) == "absent"
    assert a.check("") == "absent"
    assert a.check("Basic abc") == "absent"
    assert a.check("Bearer ${MCP_PROXY_TOKEN}") == "invalid"
    assert a.check(f"Bearer {OTHER}") == "invalid"


def test_counters(tmp_path: Path) -> None:
    a = make(tmp_path, "audit")
    a.count("absent")
    a.count("invalid")
    a.count("invalid")
    a.count("bad_host")
    snap = a.snapshot()
    assert snap == {
        "auth": "audit",
        "unauth": 3,
        "unauth_absent": 1,
        "unauth_invalid": 2,
        "bad_host": 1,
    }


def test_counting_never_logs_the_token(tmp_path: Path, caplog) -> None:
    caplog.set_level("DEBUG")
    a = make(tmp_path, "audit")
    a.count("invalid")
    a.check(f"Bearer {OTHER}")
    assert TOKEN not in caplog.text
    assert OTHER not in caplog.text
