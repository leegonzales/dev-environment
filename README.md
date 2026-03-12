# dev-environment

Portable Claude Code development environment — config files, tooling setup, skills, and documented playbooks for compound workflows.

## Quick Start

```bash
git clone git@github.com:leegonzales/dev-environment.git
cd dev-environment
./bootstrap.sh
```

Then complete the manual steps printed by the script (API keys, plugin installs, GWS auth).

## What's Inside

### `claude/` — Claude Code Configuration
- `settings.json` — Permissions, hooks, plugins, env vars
- `settings.local.json` — Machine-local permission overrides
- `statusline-command.sh` — P10k-style status line for Claude Code
- `CLAUDE.md` — Global agent instructions (coding style, voice, workflows)
- `guardrails/` — Safety hooks (block dangerous commands, detect secrets)

### `launchd/` — macOS Daemon Templates
- `com.cass.index-watch.plist` — Continuous CASS session indexer
- `com.cass.semantic-reindex.plist` — Nightly semantic reindex (3 AM)
- `com.claude-speak.daemon.plist` — Kokoro TTS daemon (Apple Silicon)

### `shell/` — Shell Configuration
- `ai-tools.zsh` — AI tool aliases and PATH config (source from `.zshrc`)

### `playbooks/` — Compound Workflow Recipes
Documented pipelines for multi-skill orchestration. Written so Claude Code can read them and execute the workflows.

See [playbooks/README.md](playbooks/README.md) for the full index.

## Design Principles

1. **Repo is source of truth** — actual config files, not markdown descriptions
2. **`bootstrap.sh` is idempotent** — safe to re-run, checks before installing
3. **No secrets** — API key placeholders only, `.env.example` pattern
4. **Skills are separate** — bootstrap clones [AISkills](https://github.com/leegonzales/AISkills), doesn't bundle them
5. **Launchd plists use `__USERNAME__`** — bootstrap.sh substitutes the real username

## Verification

After bootstrap:

```bash
claude --version          # Claude Code installed
cass health               # CASS indexer running
bd --version              # Beads issue tracker
ls ~/.claude/skills/ | wc -l  # 30+ skills loaded
```

## External Repos (Cloned by Bootstrap)

### Tier 1 — Core AI Agent Infrastructure

| Repo | Destination | Purpose |
|------|-------------|---------|
| `leegonzales/AISkills` | `~/Projects/leegonzales/AISkills` | 38+ skills, symlinked to `~/.claude/skills/` |
| `leegonzales/claude-sandboxes` | `~/Projects/claude-sandboxes` | Docker sandbox system for isolated execution |
| `leegonzales/claude-speak` | `~/Projects/claude-speak` | TTS daemon (Kokoro on Apple Silicon) |
| `leegonzales/claude-guardrails` | `~/Projects/leegonzales/claude-guardrails` | Security guardrails (Rust binary, 80+ rules) |
| `leegonzales/claude-allowlist` | `~/Projects/leegonzales/claude-allowlist` | Pre-approved safe command lists |
| `leegonzales/agent-orchestra` | `~/Projects/leegonzales/agent-orchestra` | Multi-agent orchestration (Claude + Gemini workers) |

### Tier 2 — CASS + Dependencies (built from source)

| Repo | Destination | Purpose |
|------|-------------|---------|
| `leegonzales/cass` (fork of Dicklesworthstone) | `~/Projects/leegonzales/cass` | CASS — cross-agent session search + cass-monitor |
| `Dicklesworthstone/frankensearch` | `~/Projects/leegonzales/frankensearch` | Hybrid local search (lexical + vector) |
| `Dicklesworthstone/frankentui` | `~/Projects/leegonzales/frankentui` | Terminal UI kernel (Elm architecture) |
| `Dicklesworthstone/franken_agent_detection` | `~/Projects/leegonzales/franken_agent_detection` | Coding agent tool detection |
| `Dicklesworthstone/asupersync` | `~/Projects/leegonzales/asupersync` | Async runtime for Rust |
| `Dicklesworthstone/toon_rust` | `~/Projects/leegonzales/toon_rust` | Structured conversation serialization |

### Tier 3 — MCP Servers

| Repo | Destination | Purpose |
|------|-------------|---------|
| `leegonzales/google-workspace-mcp` | `~/Projects/leegonzales/google-workspace-mcp` | Google Workspace MCP server |
| `leegonzales/mcp_agent_mail` | `~/Projects/mcp_agent_mail` | Email automation MCP server |
| `leegonzales/heygen-mcp` | `~/Projects/leegonzales/heygen-mcp-fork` | HeyGen video generation MCP (optional) |

### Tier 4 — Reference

| Repo | Destination | Purpose |
|------|-------------|---------|
| `affaan-m/everything-claude-code` | `~/Projects/leegonzales/everything-claude-code` | Comprehensive Claude Code reference guide |

## Excluded

Business/client repos, ecosystem map, session history, and anything containing proprietary IP are not included. This repo contains only tooling and workflow configuration.
