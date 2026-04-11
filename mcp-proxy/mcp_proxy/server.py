"""HTTP server implementing MCP Streamable HTTP transport."""

from __future__ import annotations

import json
import logging
import uuid

from aiohttp import web

from .backend import StdioBackend

logger = logging.getLogger(__name__)


class McpHttpServer:
    """Expose a StdioBackend as a Streamable HTTP MCP endpoint."""

    def __init__(
        self,
        backend: StdioBackend,
        host: str,
        port: int,
        request_timeout: float = 60,
    ) -> None:
        self.backend = backend
        self.host = host
        self.port = port
        self.request_timeout = request_timeout
        self._sessions: set[str] = set()

        self._app = web.Application()
        self._app.router.add_post("/mcp", self.handle_post)
        self._app.router.add_get("/mcp", self.handle_get)
        self._app.router.add_delete("/mcp", self.handle_delete)
        self._app.router.add_get("/health", self.handle_health)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(
            "[%s] HTTP listening on %s:%s/mcp",
            self.backend.name,
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    # ── Handlers ─────────────────────────────────────────

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok" if self.backend.is_running else "down",
                "server": self.backend.name,
                "pid": (
                    self.backend._process.pid
                    if self.backend._process
                    else None
                ),
                "sessions": len(self._sessions),
            }
        )

    async def handle_post(self, request: web.Request) -> web.Response:
        if request.content_type != "application/json":
            return web.Response(status=415, text="expected application/json")

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.Response(status=400, text="invalid JSON")

        # Batch
        if isinstance(body, list):
            results: list[dict] = []
            session_id: str | None = None
            for msg in body:
                result, sid = await self._dispatch(msg)
                if sid:
                    session_id = sid
                if result is not None:
                    results.append(result)
            headers = self._make_headers(session_id or request.headers.get("Mcp-Session-Id"))
            if results:
                return web.json_response(
                    results if len(results) > 1 else results[0],
                    headers=headers,
                )
            return web.Response(status=202, headers=headers)

        # Single message
        result, session_id = await self._dispatch(body)
        headers = self._make_headers(session_id or request.headers.get("Mcp-Session-Id"))
        if result is not None:
            return web.json_response(result, headers=headers)
        return web.Response(status=202, headers=headers)

    async def handle_get(self, request: web.Request) -> web.Response:
        return web.Response(status=405, text="SSE not supported by this proxy")

    async def handle_delete(self, request: web.Request) -> web.Response:
        sid = request.headers.get("Mcp-Session-Id")
        if sid:
            self._sessions.discard(sid)
        return web.Response(status=200)

    # ── Dispatch ─────────────────────────────────────────

    async def _dispatch(self, msg: dict) -> tuple[dict | None, str | None]:
        """Route one JSON-RPC message. Returns (response, new_session_id)."""
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params")

        # Notification (no id)
        if msg_id is None:
            if method and method != "notifications/initialized":
                try:
                    await self.backend.send_notification(method, params)
                except Exception:
                    logger.exception("[%s] failed forwarding notification %s", self.backend.name, method)
            return None, None

        # initialize — cached
        if method == "initialize":
            return await self._handle_initialize(msg_id, params)

        # Regular request — forward with ID remapping
        return await self._handle_request(msg_id, method, params), None

    async def _handle_initialize(
        self, client_id: int | str, params: dict | None
    ) -> tuple[dict, str]:
        """Return cached init result + new session ID."""
        try:
            cached = await self.backend.initialize()
            session_id = str(uuid.uuid4())
            self._sessions.add(session_id)

            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "result": cached.get("result", {}),
            }, session_id
        except Exception as e:
            logger.exception("[%s] initialize failed", self.backend.name)
            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "error": {"code": -32603, "message": f"init failed: {e}"},
            }, ""

    async def _handle_request(
        self,
        client_id: int | str,
        method: str | None,
        params: dict | None,
    ) -> dict:
        """Forward request with ID remapping."""
        if not method:
            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "error": {"code": -32600, "message": "missing method"},
            }

        try:
            upstream = await self.backend.send_request(
                method, params, timeout=self.request_timeout
            )
            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "result": upstream.get("result"),
                **({"error": upstream["error"]} if "error" in upstream else {}),
            }
        except TimeoutError:
            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "error": {"code": -32603, "message": f"timeout after {self.request_timeout}s"},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": client_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _make_headers(self, session_id: str | None) -> dict[str, str]:
        h: dict[str, str] = {}
        if session_id:
            h["Mcp-Session-Id"] = session_id
        return h
