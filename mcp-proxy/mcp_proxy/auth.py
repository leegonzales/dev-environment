"""Bearer-token auth and Host check for the proxy's HTTP endpoints.

Modes, per server:

* ``off``     no checks, no counting (the behaviour before this module).
* ``audit``   every request is served; requests without a valid token and
              requests with a foreign Host header are counted, never blocked.
* ``enforce`` a missing or wrong token gets 401; a foreign Host gets 421.

The token lives in a file (default ``~/.config/mcp-proxy/token``, mode 0600).
It is re-read when the file changes, so rotation needs no restart. After a
rotation, ``<token file>.prev`` (also 0600) is accepted for 24 hours.

Nothing here logs or returns a token, a header value, or a request body.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

MODES = ("off", "audit", "enforce")
MIN_TOKEN_LEN = 20
PREV_GRACE_S = 24 * 60 * 60
LOG_EVERY_S = 60.0

DEFAULT_TOKEN_FILE = Path("~/.config/mcp-proxy/token").expanduser()


def parse_bearer(header: str | None) -> str | None:
    """Return the token from an ``Authorization: Bearer <token>`` value."""
    if not header:
        return None
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _b(value: str) -> bytes:
    """Bytes for a header or file value. aiohttp hands non-UTF-8 header bytes
    over as lone surrogates; ``surrogateescape`` turns them back into bytes
    instead of raising."""
    return value.encode("utf-8", "surrogateescape")


def _file_problem(path: Path) -> str | None:
    """Why this file cannot be trusted as a token file, or None if it can."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return f"token file missing: {path}"
    except OSError as exc:
        return f"token file unreadable: {path} ({exc.__class__.__name__})"
    if st.st_mode & 0o077:
        return f"token file mode must be 0600 (no group or other access): {path}"
    return None


def _read_token(path: Path) -> str | None:
    try:
        value = path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value if len(value) >= MIN_TOKEN_LEN else None


class TokenStore:
    """Reads the current token (and a recent previous one) from files."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self.prev_path = self.path.with_name(self.path.name + ".prev")
        self._clock = clock
        self._cache: dict[Path, tuple[tuple[int, ...], str | None]] = {}
        self._state: str | None = None  # last logged problem with the current file

    def _load(self, path: Path) -> str | None:
        """Token from a trusted file, cached until the file changes."""
        if _file_problem(path):
            self._cache.pop(path, None)
            return None
        try:
            st = path.stat()
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_ctime_ns, st.st_ino, st.st_size)
        hit = self._cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        token = _read_token(path)
        self._cache[path] = (key, token)
        return token

    def _note_state(self, token: str | None) -> None:
        """Log (path and reason only, never content) when the current token
        file becomes unusable or usable again, once per change."""
        state = None if token else (_file_problem(self.path) or "token file empty or too short")
        if state == self._state:
            return
        if state:
            logger.warning(
                "auth: %s; a server in enforce mode refuses requests until fixed",
                state,
            )
        else:
            logger.info("auth: token file usable again: %s", self.path)
        self._state = state

    def problem(self) -> str | None:
        """Why the current token file is unusable, or None."""
        p = _file_problem(self.path)
        if p:
            return p
        if _read_token(self.path) is None:
            return f"token file empty or too short (need {MIN_TOKEN_LEN}+ characters): {self.path}"
        return None

    def read_token(self) -> str | None:
        """The current token, for the proxy's own status check."""
        return self._load(self.path)

    def _candidates(self) -> list[str]:
        out: list[str] = []
        cur = self._load(self.path)
        self._note_state(cur)
        if cur:
            out.append(cur)
        try:
            # ctime, not mtime: `mv token token.prev` keeps the old mtime but
            # updates ctime, so the grace runs from the rotation.
            fresh = self._clock() - self.prev_path.stat().st_ctime <= PREV_GRACE_S
        except OSError:
            fresh = False
        if fresh:
            prev = self._load(self.prev_path)
            if prev:
                out.append(prev)
        return out

    def verify(self, presented: str) -> bool:
        if not presented:
            return False
        got = _b(presented)
        ok = False
        # Compare against every candidate: no early exit on a match.
        for cand in self._candidates():
            if hmac.compare_digest(got, _b(cand)):
                ok = True
        return ok


class Authenticator:
    """One per proxied server: mode, Host check, token check, counters."""

    def __init__(self, mode: str, store: TokenStore, port: int, name: str) -> None:
        if mode not in MODES:
            raise ValueError(f"auth mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.store = store
        self.port = port
        self.name = name
        self._allowed_hosts = {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
        }
        self._counts = {"absent": 0, "invalid": 0, "bad_host": 0}
        self._last_log = 0.0

    # ── checks ───────────────────────────────────────────

    def host_ok(self, host: str | None) -> bool:
        return bool(host) and host.lower() in self._allowed_hosts

    def check(self, header: str | None) -> str:
        """``ok``, ``absent`` (no usable Bearer header) or ``invalid``.

        Total: an unexpected error counts as ``invalid`` (audit still serves
        the request; enforce refuses it). Only the exception class is logged.
        """
        try:
            return self._check_inner(header)
        except Exception as exc:  # noqa: BLE001 - must never crash a request
            logger.error("[%s] auth check failed: %s", self.name, exc.__class__.__name__)
            return "invalid"

    def _check_inner(self, header: str | None) -> str:
        presented = parse_bearer(header)
        if presented is None:
            return "absent"
        return "ok" if self.store.verify(presented) else "invalid"

    # ── counters ─────────────────────────────────────────

    def count(self, kind: str) -> None:
        if kind not in self._counts:
            raise ValueError(kind)
        self._counts[kind] += 1
        now = time.monotonic()
        if now - self._last_log >= LOG_EVERY_S:
            self._last_log = now
            s = self.snapshot()
            logger.warning(
                "[%s] auth %s: %d requests without a valid token "
                "(%d none, %d wrong), %d with a foreign Host header",
                self.name,
                self.mode,
                s["unauth"],
                s["unauth_absent"],
                s["unauth_invalid"],
                s["bad_host"],
            )

    def snapshot(self) -> dict[str, int | str]:
        c = self._counts
        return {
            "auth": self.mode,
            "unauth": c["absent"] + c["invalid"],
            "unauth_absent": c["absent"],
            "unauth_invalid": c["invalid"],
            "bad_host": c["bad_host"],
        }
