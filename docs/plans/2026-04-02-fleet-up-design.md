# fleet-up: Agent Fleet Launcher

> **Status:** Approved
> **Date:** 2026-04-02
> **Location:** `~/Projects/leegonzales/dev-environment/fleet-up/`

---

## Problem

After every reboot, Lee must manually open terminals, `cd` into repos, and launch Claude Code sessions for his agent fleet. This takes 15-20 minutes and is error-prone. The fleet has grown to 22+ agent sessions across 4 logical screens, making manual setup unsustainable.

Secondary goal: maximize daily Claude Code token utilization by keeping the full fleet warm and ready.

## Solution

A config-driven launcher (`fleet-up`) that:

1. Creates named tmux sessions per agent
2. Opens labeled Ghostty windows
3. Uses AeroSpace to tile windows across workspaces
4. Supports two display modes (Samsung 42" TV, MacBook 14")
5. Auto-launches `claude --permission-mode bypassPermissions` in each session
6. Is idempotent — safe to re-run, reattaches existing sessions

## Dependencies

| Tool | Purpose | Install |
|------|---------|---------|
| **Ghostty** | Terminal emulator | Already installed |
| **tmux 3.6** | Session persistence | Already installed |
| **AeroSpace** | Tiling WM, workspace management | `brew install --cask aerospace` |
| **Python 3.12+** | Launcher script | Already installed |

## Display Modes

### Samsung 42" TV (`--mode samsung`)

6 terminals per workspace, 4 workspaces. 2x3 grid per workspace.

```
+----------+----------+----------+
|          |          |          |
|    1     |    2     |    3     |
|          |          |          |
+----------+----------+----------+
|          |          |          |
|    4     |    5     |    6     |
|          |          |          |
+----------+----------+----------+
```

### MacBook 14" (`--mode macbook`)

4 terminals per workspace, 6 workspaces. 2x2 grid per workspace.

```
+----------------+----------------+
|                |                |
|       1        |       2        |
|                |                |
+----------------+----------------+
|                |                |
|       3        |       4        |
|                |                |
+----------------+----------------+
```

## Screen Layout — Samsung Mode

### Workspace 1: Command

| Slot | Agent | tmux session | Repo |
|------|-------|-------------|------|
| 1 | Adama | `adama` | `~/Projects/leegonzales/servitor` |
| 2 | Dax-1 | `dax-1` | `~/Projects/catalyst/bizops` |
| 3 | Dax-2 | `dax-2` | `~/Projects/catalyst/bizops` |
| 4 | Alfred-1 | `alfred-1` | `~/Projects/leegonzales/alfred` |
| 5 | Alfred-2 | `alfred-2` | `~/Projects/leegonzales/alfred` |
| 6 | cass-monitor | `cass-cmd` | *(runs `cass monitor`)* |

### Workspace 2: Training

| Slot | Agent | tmux session | Repo |
|------|-------|-------------|------|
| 1 | Walsh-1 | `walsh-1` | `~/Projects/leegonzales/AIEnablementTraining` |
| 2 | Walsh-2 | `walsh-2` | `~/Projects/leegonzales/range-framework` |
| 3 | Dax-3 | `dax-3` | `~/Projects/catalyst/bizops` |
| 4 | Workbench | `workbench` | `~/Projects` |
| 5 | cass-monitor | `cass-trn` | *(runs `cass monitor`)* |
| 6 | *(open)* | — | — |

### Workspace 3: Media Empire

| Slot | Agent | tmux session | Repo |
|------|-------|-------------|------|
| 1 | Reith | `reith` | `~/Projects/leegonzales/reith` |
| 2 | Sisko | `sisko` | `~/Projects/leegonzales/sisko` |
| 3 | Burke | `burke` | `~/Projects/leegonzales/substack` |
| 4 | Carl | `carl` | `~/Projects/leegonzales/ai-talkshow-cli` |
| 5 | Elliot | `elliot` | `~/Projects/leegonzales/ElliotSkyFallDailyWeather` |
| 6 | cass-monitor | `cass-med` | *(runs `cass monitor`)* |

### Workspace 4: Tools & Twin

| Slot | Agent | tmux session | Repo |
|------|-------|-------------|------|
| 1 | Pike | `pike` | `~/Projects/leegonzales/everything-claude-code` |
| 2 | Geordi | `geordi` | `~/Projects/leegonzales/cass` |
| 3 | SecondBrain | `secondbrain` | `~/Projects/leegonzales/SecondBrain` |
| 4 | Data | `data` | `~/Projects/leegonzales/SiliconDoppelgangerActual` |
| 5 | cass-monitor | `cass-tools` | *(runs `cass monitor`)* |
| 6 | *(open)* | — | — |

## Screen Layout — MacBook Mode

Same agents, reflowed into 2x2 grids across 6 workspaces:

| WS | Agents |
|----|--------|
| 1 | Adama, Dax-1, Dax-2, Alfred-1 |
| 2 | Alfred-2, Walsh-1, Walsh-2, Dax-3 |
| 3 | Workbench, Reith, Sisko, Burke |
| 4 | Carl, Elliot, Pike, Geordi |
| 5 | SecondBrain, Data, cass-monitor, *(open)* |
| 6 | *(overflow / ad-hoc)* |

cass-monitor runs once in MacBook mode (not per-screen).

## Architecture

```
fleet-up/
├── fleet_up.py          # Main launcher script
├── config.toml          # Agent definitions, screen layouts, display modes
├── aerospace.toml       # Generated AeroSpace config (workspaces, keybindings)
└── README.md            # Usage docs
```

### config.toml structure

```toml
[display.samsung]
grid = [3, 2]           # cols x rows per workspace
workspaces = 4

[display.macbook]
grid = [2, 2]
workspaces = 6

[[agents]]
name = "adama"
label = "Adama | Fleet Commander"
repo = "~/Projects/leegonzales/servitor"
screen = "command"
claude = true            # auto-launch claude

[[agents]]
name = "dax-1"
label = "Dax-1 | BizOps"
repo = "~/Projects/catalyst/bizops"
screen = "command"
claude = true

[[agents]]
name = "workbench"
label = "Workbench | Lee"
repo = "~/Projects"
screen = "training"
claude = false           # just a shell

[[agents]]
name = "cass-cmd"
label = "cass monitor | Command"
repo = "~/Projects"
screen = "command"
command = "cass monitor"  # custom command instead of claude
```

### Launch sequence

1. **Detect display** — check connected displays, auto-select mode (or accept `--mode` flag)
2. **Ensure AeroSpace running** — start if needed, apply workspace config
3. **Create tmux sessions** — for each agent, skip if session already exists (idempotent)
4. **Open Ghostty windows** — one per agent, with title set to agent label
5. **Attach tmux** — each Ghostty window attaches to its tmux session
6. **Position windows** — AeroSpace moves each window to correct workspace + grid slot
7. **Launch claude** — in sessions where `claude = true`, send the launch command via tmux

### Ghostty window labeling

Each Ghostty window gets a descriptive title via tmux:
```
tmux rename-window -t adama "Adama | Fleet Commander"
```

The tmux status bar shows: `[agent-name] repo-basename`

### Idempotency rules

- If tmux session exists: reattach, don't recreate
- If Ghostty window exists for session: focus it, don't open another
- If claude is already running in session: leave it alone
- If AeroSpace workspace already has windows: rearrange, don't duplicate

## CLI Interface

```bash
# Full fleet launch (auto-detect display)
fleet-up

# Explicit display mode
fleet-up --mode samsung
fleet-up --mode macbook

# Launch specific screen only
fleet-up --screen command
fleet-up --screen media-empire

# Launch single agent
fleet-up --agent adama

# Status: show what's running
fleet-up --status

# Teardown (kill tmux sessions, close windows)
fleet-up --down

# Teardown single screen
fleet-up --down --screen training
```

## Display Detection

```python
# Use system_profiler to detect connected displays
# Samsung 42" reports as ~3840x2160 or similar
# MacBook 14" built-in is 3024x1964 (or scaled)
# If external display detected: samsung mode
# If only built-in: macbook mode
# --mode flag overrides detection
```

## AeroSpace Configuration

fleet-up generates/updates `~/.aerospace.toml` with:
- 4-6 named workspaces matching screen names
- Keybindings: `alt+1` through `alt+6` to switch workspaces
- Tiling mode: BSP (binary space partitioning) per workspace
- Gaps: 8px between windows for visual separation

## Error Handling

- Missing repo directory: warn and skip agent, don't abort
- tmux session creation failure: retry once, then skip with warning
- AeroSpace not running: start it, wait 2s, retry
- Claude launch failure: log error, leave tmux session open for manual intervention
- Partial launch: `--status` shows what succeeded and what failed

## Testing

- Unit tests for config parsing, display detection, tmux session management
- Integration test: launch 2 agents, verify tmux sessions exist, teardown
- Manual verification on both Samsung and MacBook displays

## Future Enhancements (not in v1)

- Token usage dashboard (integrate with `cass analytics`)
- Auto-dispatch work to idle agents
- Fleet health monitoring (which agents are active vs idle)
- Keyboard shortcuts to cycle through agent workspaces
- Agent grouping presets ("morning routine", "deep work", "media day")
