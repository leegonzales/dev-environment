"""Stdio backend — manages a single MCP server child process with request multiplexing."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class StdioBackend:
    """Spawn one stdio MCP server, multiplex N callers onto it via ID remapping."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.env = env

        self._process: asyncio.subprocess.Process | None = None
        self._next_id: int = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._write_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None

        self._initialized: bool = False
        self._init_result: dict | None = None
        self._init_lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Spawn the stdio child process."""
        child_env = os.environ.copy()
        if self.env:
            child_env.update(self.env)

        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
        )
        self._reader_task = asyncio.create_task(
            self._read_loop(), name=f"{self.name}-reader"
        )
        self._stderr_task = asyncio.create_task(
            self._stderr_loop(), name=f"{self.name}-stderr"
        )
        logger.info("[%s] started PID %s", self.name, self._process.pid)

    async def stop(self) -> None:
        """Gracefully stop the child process."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._process and self._process.returncode is None:
            try:
                assert self._process.stdin
                self._process.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    self._process.kill()

        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("backend stopped"))
        self._pending.clear()
        logger.info("[%s] stopped", self.name)

    # ── stdio I/O ────────────────────────────────────────

    async def _read_loop(self) -> None:
        """Read stdout line-by-line, dispatch responses by id."""
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    logger.warning("[%s] stdout closed (process exited?)", self.name)
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("[%s] non-JSON stdout: %r", self.name, line[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
                elif msg_id is not None:
                    logger.warning(
                        "[%s] response for unknown id %s", self.name, msg_id
                    )
                else:
                    logger.debug(
                        "[%s] server notification: %s", self.name, msg.get("method")
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[%s] reader crashed", self.name)

    async def _stderr_loop(self) -> None:
        """Drain stderr to logs (WARNING level so crashes are visible)."""
        assert self._process and self._process.stderr
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.warning("[%s] stderr: %s", self.name, line.decode().rstrip())
        except asyncio.CancelledError:
            pass

    async def _write(self, msg: dict) -> None:
        """Write one JSON-RPC message to stdin (serialized)."""
        assert self._process and self._process.stdin
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        async with self._write_lock:
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()

    # ── public API ───────────────────────────────────────

    def _alloc_id(self) -> int:
        uid = self._next_id
        self._next_id += 1
        return uid

    async def send_request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = 60,
    ) -> dict:
        """Send a JSON-RPC request to the backend, return the response."""
        uid = self._alloc_id()
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": uid, "method": method}
        if params is not None:
            msg["params"] = params

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[uid] = fut

        try:
            await self._write(msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(uid, None)
            raise

    async def send_notification(
        self, method: str, params: dict | None = None
    ) -> None:
        """Send a JSON-RPC notification (fire-and-forget)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._write(msg)

    async def initialize(self) -> dict:
        """Initialize the upstream server (cached after first call)."""
        async with self._init_lock:
            if self._initialized:
                assert self._init_result is not None
                return self._init_result

            params = {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "mcp-proxy-mux", "version": "0.1.0"},
            }
            response = await self.send_request("initialize", params, timeout=30)

            await self.send_notification("notifications/initialized")

            self._initialized = True
            self._init_result = response
            server_info = response.get("result", {}).get("serverInfo", {})
            logger.info("[%s] initialized: %s", self.name, server_info)
            return response

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None
