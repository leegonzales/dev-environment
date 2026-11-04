"""Configuration loading for mcp-proxy-mux."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .auth import DEFAULT_TOKEN_FILE, MODES

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class ServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    port: int = 9100
    auth: str | None = None  # None: use [proxy] auth


@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    request_timeout: float = 60.0
    servers: list[ServerConfig] = field(default_factory=list)
    auth: str = "audit"
    token_file: Path = DEFAULT_TOKEN_FILE

    def auth_for(self, server: ServerConfig) -> str:
        return server.auth or self.auth


def _check_mode(mode: Any, where: str) -> str:
    if mode not in MODES:
        raise ValueError(f"{where}: auth must be one of {MODES}, got {mode!r}")
    return mode


def _load_env_file(path_str: str) -> dict[str, str]:
    """Load KEY=VALUE pairs from a .env file, expanding ~ and ignoring comments."""
    env_path = Path(path_str).expanduser()
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value
    return result


def load_config(path: Path) -> ProxyConfig:
    """Load proxy configuration from a TOML file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    proxy_section: dict[str, Any] = raw.get("proxy", {})
    host = proxy_section.get("host", "127.0.0.1")
    timeout = proxy_section.get("request_timeout", 60.0)
    auth = _check_mode(proxy_section.get("auth", "audit"), "[proxy]")
    token_file = Path(
        proxy_section.get("token_file", str(DEFAULT_TOKEN_FILE))
    ).expanduser()
    if not token_file.is_absolute():
        # launchd starts the proxy with cwd "/", so a relative path would
        # silently point somewhere else.
        raise ValueError(f"[proxy]: token_file must be an absolute path, got {token_file}")

    servers: list[ServerConfig] = []
    for name, cfg in raw.get("servers", {}).items():
        env: dict[str, str] = {}
        # Load env files first (base layer)
        for env_file in cfg.get("env_files", []):
            env.update(_load_env_file(env_file))
        # Explicit env vars override env_files
        env.update(cfg.get("env", {}))

        servers.append(
            ServerConfig(
                name=name,
                command=cfg["command"],
                args=cfg.get("args", []),
                env=env,
                port=cfg["port"],
                auth=(
                    _check_mode(cfg["auth"], f"[servers.{name}]")
                    if "auth" in cfg
                    else None
                ),
            )
        )

    return ProxyConfig(
        host=host,
        request_timeout=timeout,
        servers=servers,
        auth=auth,
        token_file=token_file,
    )
