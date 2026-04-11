# MCP Proxy Mux — Design

> Multiplexing proxy that wraps stdio MCP servers as shared HTTP endpoints, so 17+ Claude Code agents share one process per server instead of each spawning their own.

## Problem

With 17 Claude Code agents (fleet-up), every stdio MCP server is spawned per-instance:

| Server | Type | At 17 agents |
|--------|------|-------------|
| google-workspace-personal | stdio (node) | 17 processes |
| google-workspace | stdio (node) | 17 processes |
| nanobanana-mcp | stdio (node) | 17 processes |
| brave-search | stdio (npx) | 34 processes (node + npx) |
| netlify | stdio (npx) | 34 processes |
| veo-mcp | stdio (node) | 17 processes |
| chrome-devtools | stdio (npx) | 34 processes + watchdogs |
| playwright | stdio (npx) | 34 processes |
| **Total** | | **~187 processes** |

Already-shared servers (HTTP): mcp-agent-mail, imessage, maps-grounding-lite, stripe.

Per-agent-identity (can't share): mattermost-channel (unique bot tokens per agent).

## Solution

A Python asyncio service that:
1. Spawns **one** stdio child process per configured server
2. Exposes each as an **HTTP Streamable MCP endpoint** on localhost
3. **Multiplexes** requests from all Claude Code instances onto the single backend
4. **Remaps JSON-RPC IDs** to prevent collisions between concurrent callers

### Safe to wrap (stateless API calls)
- google-workspace-personal (port 9100)
- google-workspace (port 9101)
- nanobanana-mcp (port 9102)
- brave-search (port 9103)
- netlify (port 9104)
- veo-mcp (port 9105)

### Not safe to wrap
- chrome-devtools, playwright — browser session state would conflict
- mattermost-channel — per-agent identity (different bot tokens)

### Savings: 6 servers x 16 eliminated copies = ~96 fewer processes

## Architecture

```
Claude Code 1 ──POST /mcp──┐
Claude Code 2 ──POST /mcp──┤
  ...                       ├── HTTP Server (:port)
Claude Code N ──POST /mcp──┤      │
                            │  ID Remap + Route
                            │      │
                            │  Single stdio process
                            │  (stdin → JSON-RPC → stdout)
                            └─────────────────────────
```

### Key Mechanisms

1. **ID Remapping**: Each client sends their own `id` values. Proxy assigns globally unique upstream IDs, maintains a mapping table, translates responses back.

2. **Initialize Caching**: First client triggers real `initialize` + `notifications/initialized`. All subsequent clients get the cached `InitializeResult`.

3. **Stdin Serialization**: asyncio.Lock ensures one message written at a time (stdio is a single stream).

4. **Response Routing**: Dedicated reader task parses stdout line-by-line, dispatches by `id` to waiting asyncio.Futures.

## Components

```
mcp-proxy/
├── config.toml              # Server definitions (command, args, env, port)
├── pyproject.toml            # Python package (aiohttp dependency)
├── mcp_proxy/
│   ├── backend.py            # StdioBackend — child process + multiplexing
│   ├── server.py             # McpHttpServer — HTTP Streamable transport
│   ├── config.py             # TOML config loading
│   └── cli.py                # CLI entry point
└── tests/
    ├── test_config.py         # Config loading tests
    ├── test_backend.py        # Backend unit tests (fake MCP server)
    ├── test_server.py         # HTTP integration tests (fake server)
    └── test_real_server.py    # Real MCP server integration tests
```

## Migration Path

Current settings.json entries (stdio):
```json
"nanobanana-mcp": {
  "command": "node",
  "args": ["/path/to/nanobanana-mcp/dist/index.js"]
}
```

After proxy is running, change to (HTTP):
```json
"nanobanana-mcp": {
  "type": "http",
  "url": "http://127.0.0.1:9102/mcp"
}
```

The proxy handles all the stdio management. Claude Code sees a standard HTTP MCP server.

## Future Work

- **Launchd daemon**: Auto-start proxy at boot (before fleet-up)
- **Health monitoring**: Restart crashed backends automatically
- **fleet-up integration**: `fleet-up` starts proxy as pre-step
- **Chrome/Playwright pooling**: Shared pool with locking for browser-state servers
