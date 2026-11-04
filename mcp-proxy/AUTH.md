# mcp-proxy-mux: token auth and Host check

Why: the proxy listens on `127.0.0.1:9100-9107` and used to answer anyone who could reach
loopback, including containers on this Mac (via `host.docker.internal`). Bead servitor-zjyt2.

## Modes (`[proxy] auth`, overridable per `[servers.<name>] auth`)

| Mode | Behaviour |
|---|---|
| `off` | No checks, no counting. |
| `audit` (default) | Serves every request. Counts requests with no valid token (`unauth_absent`, `unauth_invalid`) and with a foreign Host header (`bad_host`). Blocks nothing. |
| `enforce` | Missing or wrong token: 401. Host not `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>`: 421. `/health` shows only status to a caller without the token. |

**Watch in the audit window: containers.** The Host check expects `127.0.0.1:<port>`,
`localhost:<port>` or `[::1]:<port>`. A container that reaches the proxy through
`host.docker.internal:<port>` sends a different Host, so it shows up as `bad_host` in audit and
gets 421 under `enforce`. If `--status` shows `bad_host` above 0 after every pane has switched,
find the client before flipping to `enforce`: either it should not be using the proxy, or it must
send `Host: 127.0.0.1:<port>`. A container with no business here is the case this check exists for.

A mode other than these three stops the proxy at load (no silent fallback). `enforce` with a
missing, empty, short (under 20 characters) or group/other-readable token file stops it at start
(exit 2) before any backend is spawned.

## Token file

`token_file` under `[proxy]`, default `~/.config/mcp-proxy/token`, mode 0600, absolute path (a
relative one is refused: launchd starts the proxy in `/`). The proxy re-reads it when it changes,
so rotation needs no restart. `<token_file>.prev` (0600) is also accepted for 24 h from the moment
it was created or renamed (the file's change time, so `mv` counts). The token is never logged,
printed, or returned. If the file is deleted, loosened or emptied while the proxy runs, `enforce`
refuses every request and the log says why (path and reason, once per change).

Create (once):

    mkdir -p ~/.config/mcp-proxy && chmod 700 ~/.config/mcp-proxy
    python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/mcp-proxy/token
    chmod 600 ~/.config/mcp-proxy/token

Rotate: `mv token token.prev` (keep 0600), write a new `token` the same way, then update clients
within 24 h.

## Client step (Claude Code)

Tested in a scratch config (`CLAUDE_CONFIG_DIR`): a user-scope http entry expands `${VAR}` in
`headers`, so the secret stays in one file. Export it in the shell startup file every pane reads:

    export MCP_PROXY_TOKEN="$(cat ~/.config/mcp-proxy/token)"

For each of the 8 entries (name and URL **before** `--header`, which is variadic):

    claude mcp remove --scope user <name>
    claude mcp add --scope user --transport http <name> http://127.0.0.1:<port>/mcp \
      --header 'Authorization: Bearer ${MCP_PROXY_TOKEN}'

Use single quotes so the shell does not expand it. The entry stores the literal `${MCP_PROXY_TOKEN}`.
A pane started without the variable sends the literal template: Claude Code warns "Missing
environment variables", the proxy counts it as `unauth_invalid`, and under `enforce` the
client reports HTTP 401 with this proxy's message.

## Reading the counters

`mcp-proxy-mux --status` sends the token (if the file is usable) and prints
`auth=<mode> unauth=<n> [bad_host=<n>]` per server. The proxy logs a summary line at most once a
minute while the counts are non-zero; the line holds counts only.

Flip to `enforce` when `unauth` and `bad_host` stay at 0 for 24 h after every client has switched.
Rollback: set `auth = "off"` (or `"audit"`) and restart the proxy; clients need no change.

## Not covered

Code running as the same user can read the token file. This stops other accounts, containers,
sandboxed tools and DNS-rebinding pages, not a process running as you.

A container that bind-mounts your home directory can read the token file, and one that inherits
your environment (`docker run -e MCP_PROXY_TOKEN`, `--env-file`) gets the token. Keep the token out
of container mounts and env passthrough.

An event stream opened before a rotation keeps running after the old token expires (the check runs
per request). `/health` in `audit` also lists the counters; only the extra keys differ from `off`.
