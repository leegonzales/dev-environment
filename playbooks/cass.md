# CASS — Coding Agent Session Search

## What It Does

Indexes all local coding agent sessions (Claude Code, Codex, Gemini, Cursor, OpenCode) into a single searchable database. Enables cross-agent recall: "when did I solve this before?", "what approach did I use for X?".

## Prerequisites

- CASS installed (`brew install dicklesworthstone/tap/cass`)
- launchd plists installed (handled by bootstrap.sh)

## Architecture

```
Agent sessions (JSONL logs)
  ├── ~/.claude/projects/*/     # Claude Code
  ├── ~/.codex/sessions/        # Codex
  ├── ~/.gemini/sessions/       # Gemini
  └── ~/.cursor/sessions/       # Cursor
       │
       ▼
  com.cass.index-watch (launchd)  ← continuous indexer
       │
       ▼
  ~/.local/share/cass/index/      ← SQLite FTS5 + semantic embeddings
       │
       ▼
  cass search / cass tui           ← query interface
```

## How to Run

### Search modes
```bash
cass search "wardley map"              # Lexical (exact keywords, fastest)
cass search "wardley map" --mode semantic  # Meaning-based (MiniLM embeddings)
cass search "wardley map" --mode hybrid    # Fuses both (best for broad queries)
```

### Find sessions related to a file
```bash
cass context src/main.rs               # Sessions that touched this file
```

### Interactive TUI
```bash
cass tui                               # Full-text search with preview
```

### Health check
```bash
cass health                            # Verify indexer and database status
```

### Manual reindex
```bash
cass index                             # One-shot reindex
cass index --semantic                  # Rebuild semantic embeddings (slow)
```

## Launchd Daemons

| Plist | Schedule | Purpose |
|-------|----------|---------|
| `com.cass.index-watch` | Always running | Watches for new sessions, indexes continuously |
| `com.cass.semantic-reindex` | Daily at 3 AM | Rebuilds semantic embeddings (pauses watcher first) |

### Managing daemons
```bash
launchctl list | grep cass             # Check status
launchctl unload ~/Library/LaunchAgents/com.cass.index-watch.plist  # Stop
launchctl load ~/Library/LaunchAgents/com.cass.index-watch.plist    # Start
```

## Tips

- Semantic search runs locally (MiniLM embeddings) — no API cost
- The nightly reindex pauses the watcher to avoid conflicts
- Logs at `~/Library/Logs/cass-index.log` and `~/Library/Logs/cass-semantic-reindex.log`
- If search feels stale, check `cass health` — the watcher may have crashed
