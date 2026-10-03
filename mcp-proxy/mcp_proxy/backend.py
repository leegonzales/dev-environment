"""Stdio backend — manages a single MCP server child process with request multiplexing."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# asyncio's default StreamReader limit is 64 KiB per line. One JSON-RPC
# response routinely exceeds that (a Gmail message, a Sheets range, a base64
# image), and an overrun kills the reader — after which every request from
# every session hangs until it times out. Lines are bounded by this instead.
STREAM_LIMIT = 64 * 1024 * 1024

# Respawn backoff after the child dies: 0.5s, 1s, 2s ... capped at 30s.
RESPAWN_BASE_DELAY = 0.5
RESPAWN_MAX_DELAY = 30.0


class BackendUnavailable(RuntimeError):
    """The child process died or could not be reached; the call can be retried."""


class StdioBackend:
    """Spawn one stdio MCP server, multiplex N callers onto it via ID remapping.

    The child is supervised: if it exits or its stdout reader fails, in-flight
    requests fail immediately and a fresh child is spawned (with backoff) and
    re-initialized, so one bad tool call cannot take the server down for every
    connected session.
    """

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

        # Supervision state. _generation identifies the current child so a
        # stale reader from a replaced child cannot trigger a second respawn.
        self._generation: int = 0
        self._stopping: bool = False
        self._ready = asyncio.Event()
        self._respawn_task: asyncio.Task[None] | None = None
        self._consecutive_failures: int = 0

    async def start(self) -> None:
        """Spawn the stdio child process."""
        self._stopping = False
        await self._spawn()

    async def _spawn(self) -> None:
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
            limit=STREAM_LIMIT,
        )
        self._generation += 1
        gen = self._generation
        proc = self._process
        self._reader_task = asyncio.create_task(
            self._read_loop(proc, gen), name=f"{self.name}-reader"
        )
        self._stderr_task = asyncio.create_task(
            self._stderr_loop(proc), name=f"{self.name}-stderr"
        )
        self._ready.set()
        logger.info("[%s] started PID %s", self.name, proc.pid)

    async def stop(self) -> None:
        """Gracefully stop the child process."""
        self._stopping = True
        if self._respawn_task:
            self._respawn_task.cancel()
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        await self._terminate(self._process)

        self._fail_pending(BackendUnavailable("backend stopped"))
        logger.info("[%s] stopped", self.name)

    async def _terminate(self, proc: asyncio.subprocess.Process | None) -> None:
        if proc is None or proc.returncode is not None:
            return
        try:
            assert proc.stdin
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except TimeoutError:
                proc.kill()

    # ── supervision ──────────────────────────────────────

    def _fail_pending(self, exc: Exception) -> None:
        pending, self._pending = self._pending, {}
        for fut in pending.values():
            if not fut.done():
                fut.set_exception(exc)

    def _on_child_lost(self, gen: int, reason: str) -> None:
        """Fail in-flight calls now and schedule a respawn of this child."""
        if gen != self._generation or self._stopping:
            return
        logger.warning(
            "[%s] child lost (%s); failing %d in-flight request(s)",
            self.name,
            reason,
            len(self._pending),
        )
        self._ready.clear()
        self._fail_pending(BackendUnavailable(f"{self.name}: {reason}"))
        if self._respawn_task is None or self._respawn_task.done():
            self._respawn_task = asyncio.create_task(
                self._respawn(), name=f"{self.name}-respawn"
            )

    async def _respawn(self) -> None:
        delay = min(
            RESPAWN_MAX_DELAY,
            RESPAWN_BASE_DELAY * (2**self._consecutive_failures),
        )
        self._consecutive_failures += 1
        while not self._stopping:
            await asyncio.sleep(delay)
            if self._stopping:
                return
            try:
                await self._terminate(self._process)
                await self._spawn()
                if self._initialized:
                    # Clients keep the cached init result; the new child still
                    # needs its own handshake before it will serve tool calls.
                    await self._request_raw(
                        "initialize", self._init_params(), timeout=30
                    )
                    await self.send_notification("notifications/initialized")
                logger.info(
                    "[%s] respawned (attempt %d)", self.name, self._consecutive_failures
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[%s] respawn failed", self.name)
                self._ready.clear()
                delay = min(RESPAWN_MAX_DELAY, delay * 2)

    # ── stdio I/O ────────────────────────────────────────

    async def _read_loop(self, proc: asyncio.subprocess.Process, gen: int) -> None:
        """Read stdout line-by-line, dispatch responses by id."""
        assert proc.stdout
        reason = "stdout closed"
        try:
            while True:
                line = await proc.stdout.readline()
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
                    self._consecutive_failures = 0
                elif msg_id is not None:
                    logger.warning("[%s] response for unknown id %s", self.name, msg_id)
                else:
                    logger.debug(
                        "[%s] server notification: %s", self.name, msg.get("method")
                    )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("[%s] reader crashed", self.name)
            reason = f"reader crashed: {exc}"
        self._on_child_lost(gen, reason)

    async def _stderr_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Drain stderr to logs (WARNING level so crashes are visible).

        Reads fixed-size chunks rather than lines, so no line is ever too long
        and the pipe always drains — a child blocked on a full stderr pipe
        stops answering stdout, which hangs every session.
        """
        assert proc.stderr
        buf = b""
        try:
            while True:
                chunk = await proc.stderr.read(65536)
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    logger.warning(
                        "[%s] stderr: %s",
                        self.name,
                        raw[:2000].decode(errors="replace").rstrip(),
                    )
                if len(buf) > 65536:  # unterminated flood: log a slice, drop rest
                    logger.warning(
                        "[%s] stderr: %s…",
                        self.name,
                        buf[:2000].decode(errors="replace"),
                    )
                    buf = b""
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[%s] stderr drain failed", self.name)

    async def _write(self, msg: dict) -> None:
        """Write one JSON-RPC message to stdin (serialized)."""
        proc = self._process
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise BackendUnavailable(f"{self.name}: child not running")
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        async with self._write_lock:
            try:
                proc.stdin.write(data.encode())
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                self._on_child_lost(self._generation, f"stdin write failed: {exc}")
                raise BackendUnavailable(f"{self.name}: {exc}") from exc

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
        """Send a JSON-RPC request to the backend, return the response.

        If the child is being respawned, waits for it (within ``timeout``).
        Raises BackendUnavailable immediately if the child dies mid-request.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            except TimeoutError:
                raise BackendUnavailable(
                    f"{self.name}: respawn did not finish"
                ) from None
        return await self._request_raw(
            method, params, timeout=max(0.1, deadline - loop.time())
        )

    async def _request_raw(
        self, method: str, params: dict | None, timeout: float
    ) -> dict:
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
        except TimeoutError:
            self._pending.pop(uid, None)
            raise
        except BackendUnavailable:
            self._pending.pop(uid, None)
            raise

    async def send_notification(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (fire-and-forget)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._write(msg)

    @staticmethod
    def _init_params() -> dict:
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcp-proxy-mux", "version": "0.1.0"},
        }

    async def initialize(self) -> dict:
        """Initialize the upstream server (cached after first call)."""
        async with self._init_lock:
            if self._initialized:
                assert self._init_result is not None
                return self._init_result

            response = await self.send_request(
                "initialize", self._init_params(), timeout=30
            )

            await self.send_notification("notifications/initialized")

            self._initialized = True
            self._init_result = response
            server_info = response.get("result", {}).get("serverInfo", {})
            logger.info("[%s] initialized: %s", self.name, server_info)
            return response

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None
