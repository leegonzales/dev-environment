"""Tests for config loading."""

from pathlib import Path

import pytest

from mcp_proxy.config import load_config


def test_load_default_config() -> None:
    """Default config.toml loads without error."""
    path = Path(__file__).parent.parent / "config.toml"
    config = load_config(path)
    assert config.host == "127.0.0.1"
    assert config.request_timeout == 120
    assert len(config.servers) > 0


# Servers that hold per-session state must never be shared through the proxy.
STATEFUL = {"chrome-devtools", "playwright", "mattermost-channel"}


def test_no_stateful_servers_proxied() -> None:
    path = Path(__file__).parent.parent / "config.toml"
    names = {s.name for s in load_config(path).servers}
    assert not names & STATEFUL, f"stateful server in proxy: {names & STATEFUL}"


def test_every_workspace_server_has_its_profile() -> None:
    """An unset WORKSPACE_PROFILE reads a keychain entry that never existed:
    endless login windows and silent Gmail/Calendar failures. Each
    google-workspace-<org> server must set WORKSPACE_PROFILE=<org>."""
    path = Path(__file__).parent.parent / "config.toml"
    for s in load_config(path).servers:
        if s.name.startswith("google-workspace"):
            assert s.name != "google-workspace", "unsuffixed server has no profile"
            org = s.name.removeprefix("google-workspace-")
            assert (s.env or {}).get("WORKSPACE_PROFILE") == org, s.name


def test_server_names() -> None:
    path = Path(__file__).parent.parent / "config.toml"
    config = load_config(path)
    names = {s.name for s in config.servers}
    assert "google-workspace-personal" in names
    assert "nanobanana-mcp" in names
    assert "veo-mcp" in names


def test_server_ports_unique() -> None:
    path = Path(__file__).parent.parent / "config.toml"
    config = load_config(path)
    ports = [s.port for s in config.servers]
    assert len(ports) == len(set(ports)), "port collision"


def test_server_env() -> None:
    path = Path(__file__).parent.parent / "config.toml"
    config = load_config(path)
    gws = next(s for s in config.servers if s.name == "google-workspace-personal")
    assert gws.env["WORKSPACE_PROFILE"] == "personal"


def test_load_minimal_config(tmp_path: Path) -> None:
    """A config with one server loads fine."""
    toml = tmp_path / "test.toml"
    toml.write_text(
        '[proxy]\nhost = "0.0.0.0"\n\n'
        '[servers.echo]\ncommand = "cat"\nargs = []\nport = 9999\n'
    )
    config = load_config(toml)
    assert config.host == "0.0.0.0"
    assert len(config.servers) == 1
    assert config.servers[0].name == "echo"
    assert config.servers[0].port == 9999


# ── auth settings ────────────────────────────────────────


def test_auth_defaults_to_audit(tmp_path: Path) -> None:
    toml = tmp_path / "t.toml"
    toml.write_text('[servers.echo]\ncommand = "cat"\nport = 9999\n')
    config = load_config(toml)
    assert config.auth == "audit"
    assert config.token_file == Path("~/.config/mcp-proxy/token").expanduser()
    assert config.servers[0].auth is None


def test_auth_modes_and_per_server_override(tmp_path: Path) -> None:
    toml = tmp_path / "t.toml"
    toml.write_text(
        '[proxy]\nauth = "enforce"\ntoken_file = "~/x/tok"\n\n'
        '[servers.a]\ncommand = "cat"\nport = 9998\n\n'
        '[servers.b]\ncommand = "cat"\nport = 9999\nauth = "off"\n'
    )
    config = load_config(toml)
    assert config.auth == "enforce"
    assert config.token_file == Path("~/x/tok").expanduser()
    assert config.auth_for(config.servers[0]) == "enforce"
    assert config.auth_for(config.servers[1]) == "off"


@pytest.mark.parametrize("bad", ["enforse", "on", "", "ENFORCE"])
def test_bad_auth_mode_fails_loudly(tmp_path: Path, bad: str) -> None:
    toml = tmp_path / "t.toml"
    toml.write_text(f'[proxy]\nauth = "{bad}"\n\n[servers.a]\ncommand = "cat"\nport = 9999\n')
    with pytest.raises(ValueError, match="auth"):
        load_config(toml)


def test_bad_per_server_auth_mode_fails_loudly(tmp_path: Path) -> None:
    toml = tmp_path / "t.toml"
    toml.write_text('[servers.a]\ncommand = "cat"\nport = 9999\nauth = "nope"\n')
    with pytest.raises(ValueError, match="auth"):
        load_config(toml)
