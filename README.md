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

| Repo | Destination | Purpose |
|------|-------------|---------|
| `leegonzales/AISkills` | `~/Projects/leegonzales/AISkills` | Skill files symlinked to `~/.claude/skills/` |
| `leegonzales/claude-sandboxes` | `~/Projects/claude-sandboxes` | Docker sandbox system |
| `leegonzales/claude-speak` | `~/Projects/claude-speak` | TTS daemon (Kokoro on Apple Silicon) |

## Excluded

Business/client repos, ecosystem map, session history, and anything containing proprietary IP are not included. This repo contains only tooling and workflow configuration.
