"""CLI entry point for mcp-proxy-mux."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .backend import StdioBackend
from .config import ProxyConfig, load_config
from .server import McpHttpServer

logger = logging.getLogger("mcp_proxy")

DEFAULT_CONFIG = Path(__file__).parent.parent / "config.toml"


Pair = tuple[StdioBackend, McpHttpServer]

# Strong references to warm-up tasks so they are not garbage-collected.
_warm_tasks: set[asyncio.Task[None]] = set()


async def _warm(backend: StdioBackend) -> None:
    """Handshake the backend now instead of on the first client initialize.

    After a proxy restart, connected clients keep their old session ids and
    never re-send initialize; servers that enforce initialize-before-call
    would reject them until something handshakes the new child.
    """
    try:
        await backend.initialize()
    except Exception as exc:  # noqa: BLE001 - logged; the first client retries
        logger.warning("[%s] eager initialize failed: %s", backend.name, exc)


async def start_all(config: ProxyConfig) -> list[Pair]:
    """Start every configured server, isolating failures to that server.

    A backend that cannot launch keeps retrying with backoff and answers
    requests with an error. A port that cannot be bound skips only that
    server. Neither stops the rest of the proxy.
    """
    pairs: list[Pair] = []
    for sc in config.servers:
        backend = StdioBackend(
            name=sc.name,
            command=sc.command,
            args=sc.args,
            env=sc.env or None,
        )
        http = McpHttpServer(
            backend=backend,
            host=config.host,
            port=sc.port,
            request_timeout=config.request_timeout,
        )
        await backend.start()
        try:
            await http.start()
        except OSError as exc:
            logger.error(
                "[%s] cannot listen on port %s: %s; skipping", sc.name, sc.port, exc
            )
            await backend.stop()
            continue
        pairs.append((backend, http))
        # Small stagger to avoid thundering herd on npx installs
        await asyncio.sleep(0.5)

    for backend, _ in pairs:
        task = asyncio.create_task(_warm(backend), name=f"{backend.name}-warm")
        _warm_tasks.add(task)
        task.add_done_callback(_warm_tasks.discard)
    return pairs


async def stop_all(pairs: list[Pair]) -> None:
    for _, http in reversed(pairs):
        await http.stop()
    for backend, _ in reversed(pairs):
        await backend.stop()


async def run(config: ProxyConfig) -> None:
    """Start all backends and HTTP servers, run until interrupted."""
    pairs = await start_all(config)
    print_status(config, pairs)

    # Wait for shutdown signal
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("shutting down...")
    await stop_all(pairs)


def print_status(
    config: ProxyConfig, pairs: list[tuple[StdioBackend, McpHttpServer]]
) -> None:
    print("\n  mcp-proxy-mux running\n")
    for backend, http in pairs:
        pid = backend._process.pid if backend._process else "?"
        print(
            f"  {backend.name:30s}  http://{config.host}:{http.port}/mcp  (PID {pid})"
        )
    print(f"\n  {len(pairs)} servers proxied. Ctrl-C to stop.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-proxy-mux",
        description="Multiplex stdio MCP servers as shared HTTP endpoints",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="path to config.toml (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )
    parser.add_argument(
        "--server",
        type=str,
        help="start only this server (by name from config)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="check health of all proxied servers and exit",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.config.exists():
        print(f"error: config not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    config = load_config(args.config)

    if args.server:
        config.servers = [s for s in config.servers if s.name == args.server]
        if not config.servers:
            print(f"error: server '{args.server}' not in config", file=sys.stderr)
            sys.exit(1)

    if args.status:
        asyncio.run(check_status(config))
        return

    if not config.servers:
        print("no servers configured", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(config))


async def check_status(config: ProxyConfig) -> None:
    """Hit /health on each configured server."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        for sc in config.servers:
            url = f"http://{config.host}:{sc.port}/health"
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    data = await resp.json()
                    status = data.get("status", "?")
                    pid = data.get("pid", "?")
                    sessions = data.get("sessions", 0)
                    print(
                        f"  {sc.name:30s}  {status:5s}  PID {pid}  sessions={sessions}"
                    )
            except Exception:
                print(f"  {sc.name:30s}  DOWN   (not reachable on port {sc.port})")


if __name__ == "__main__":
    main()
