"""Tests for config loading."""

from pathlib import Path

from mcp_proxy.config import load_config


def test_load_default_config() -> None:
    """Default config.toml loads without error."""
    path = Path(__file__).parent.parent / "config.toml"
    config = load_config(path)
    assert config.host == "127.0.0.1"
    assert config.request_timeout == 120
    assert len(config.servers) == 5  # brave-search commented out (no API key)


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
