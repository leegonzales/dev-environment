# fleet-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a config-driven launcher that spins up Lee's full agent fleet in Ghostty + tmux + AeroSpace after reboot, with Samsung and MacBook display modes.

**Architecture:** Python CLI (`fleet-up`) reads a TOML config defining agents and screen layouts. It creates tmux sessions, opens Ghostty windows that attach to them, and uses AeroSpace CLI to move windows to named workspaces. Display mode auto-detected or overridden via flag.

**Tech Stack:** Python 3.14 (stdlib + tomllib), tmux 3.6, Ghostty, AeroSpace (brew cask)

---

### Task 1: Install AeroSpace and scaffold project

**Files:**
- Create: `fleet-up/` directory
- Create: `fleet-up/config.toml`
- Modify: `Brewfile` (add aerospace)

**Step 1: Install AeroSpace**

```bash
brew install --cask nikitabobko/tap/aerospace
```

Verify: `aerospace --version` returns a version string. AeroSpace will prompt for accessibility permissions — grant them.

**Step 2: Create project directory**

```bash
mkdir -p ~/Projects/leegonzales/dev-environment/fleet-up
```

**Step 3: Write the agent config**

Create `fleet-up/config.toml` with all agent definitions, screen assignments, and display mode grids. This is the single source of truth.

```toml
# fleet-up configuration
# All agent definitions, screen layouts, display modes

[display.samsung]
cols = 3
rows = 2
# 4 workspaces, 6 slots each

[display.macbook]
cols = 2
rows = 2
# 6 workspaces, 4 slots each

# ── Screens ──────────────────────────────────────────

[screens.command]
label = "Command"
workspace_samsung = 1
workspace_macbook = [1, 2]  # splits across 2 on macbook

[screens.training]
label = "Training"
workspace_samsung = 2
workspace_macbook = [2, 3]

[screens.media]
label = "Media Empire"
workspace_samsung = 3
workspace_macbook = [3, 4]

[screens.tools]
label = "Tools & Twin"
workspace_samsung = 4
workspace_macbook = [4, 5]

# ── Agents ───────────────────────────────────────────

[[agents]]
name = "adama"
label = "Adama | Fleet Commander"
repo = "~/Projects/leegonzales/servitor"
screen = "command"
slot = 1
claude = true

[[agents]]
name = "dax-1"
label = "Dax-1 | BizOps"
repo = "~/Projects/catalyst/bizops"
screen = "command"
slot = 2
claude = true

[[agents]]
name = "dax-2"
label = "Dax-2 | BizOps"
repo = "~/Projects/catalyst/bizops"
screen = "command"
slot = 3
claude = true

[[agents]]
name = "alfred-1"
label = "Alfred-1 | Personal Ops"
repo = "~/Projects/leegonzales/alfred"
screen = "command"
slot = 4
claude = true

[[agents]]
name = "alfred-2"
label = "Alfred-2 | Personal Ops"
repo = "~/Projects/leegonzales/alfred"
screen = "command"
slot = 5
claude = true

[[agents]]
name = "cass-cmd"
label = "cass monitor | Command"
repo = "~/Projects"
screen = "command"
slot = 6
claude = false
command = "cass monitor"

[[agents]]
name = "walsh-1"
label = "Walsh-1 | Training"
repo = "~/Projects/leegonzales/AIEnablementTraining"
screen = "training"
slot = 1
claude = true

[[agents]]
name = "walsh-2"
label = "Walsh-2 | RANGE"
repo = "~/Projects/leegonzales/range-framework"
screen = "training"
slot = 2
claude = true

[[agents]]
name = "dax-3"
label = "Dax-3 | BizOps"
repo = "~/Projects/catalyst/bizops"
screen = "training"
slot = 3
claude = true

[[agents]]
name = "workbench"
label = "Workbench | Lee"
repo = "~/Projects"
screen = "training"
slot = 4
claude = false

[[agents]]
name = "cass-trn"
label = "cass monitor | Training"
repo = "~/Projects"
screen = "training"
slot = 5
claude = false
command = "cass monitor"

[[agents]]
name = "reith"
label = "Reith | Media Coordinator"
repo = "~/Projects/leegonzales/reith"
screen = "media"
slot = 1
claude = true

[[agents]]
name = "sisko"
label = "Sisko | Strategy"
repo = "~/Projects/leegonzales/sisko"
screen = "media"
slot = 2
claude = true

[[agents]]
name = "burke"
label = "Burke | Substack"
repo = "~/Projects/leegonzales/substack"
screen = "media"
slot = 3
claude = true

[[agents]]
name = "carl"
label = "Carl | Talk Show"
repo = "~/Projects/leegonzales/ai-talkshow-cli"
screen = "media"
slot = 4
claude = true

[[agents]]
name = "elliot"
label = "Elliot | Weather"
repo = "~/Projects/leegonzales/ElliotSkyFallDailyWeather"
screen = "media"
slot = 5
claude = true

[[agents]]
name = "cass-med"
label = "cass monitor | Media"
repo = "~/Projects"
screen = "media"
slot = 6
claude = false
command = "cass monitor"

[[agents]]
name = "pike"
label = "Pike | Skills & Config"
repo = "~/Projects/leegonzales/everything-claude-code"
screen = "tools"
slot = 1
claude = true

[[agents]]
name = "geordi"
label = "Geordi | Tooling"
repo = "~/Projects/leegonzales/cass"
screen = "tools"
slot = 2
claude = true

[[agents]]
name = "secondbrain"
label = "SecondBrain | Knowledge"
repo = "~/Projects/leegonzales/SecondBrain"
screen = "tools"
slot = 3
claude = true

[[agents]]
name = "data"
label = "Data | Digital Twin"
repo = "~/Projects/leegonzales/SiliconDoppelgangerActual"
screen = "tools"
slot = 4
claude = true

[[agents]]
name = "cass-tools"
label = "cass monitor | Tools"
repo = "~/Projects"
screen = "tools"
slot = 5
claude = false
command = "cass monitor"
```

**Step 4: Add aerospace to Brewfile**

Append to `Brewfile`:
```ruby
cask "nikitabobko/tap/aerospace"
```

**Step 5: Commit**

```bash
git add fleet-up/config.toml Brewfile
git commit -m "feat: scaffold fleet-up with agent config"
```

---

### Task 2: Config loader and display detection

**Files:**
- Create: `fleet-up/fleet_up.py`
- Create: `fleet-up/tests/test_config.py`

**Step 1: Write the failing test for config loading**

Create `fleet-up/tests/__init__.py` (empty) and `fleet-up/tests/test_config.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fleet_up import load_config, detect_display_mode, agents_for_screen


def test_load_config_returns_agents():
    config = load_config(Path(__file__).parent.parent / "config.toml")
    assert len(config["agents"]) == 22
    assert config["display"]["samsung"]["cols"] == 3


def test_detect_display_mode_override():
    assert detect_display_mode(override="samsung") == "samsung"
    assert detect_display_mode(override="macbook") == "macbook"


def test_agents_for_screen():
    config = load_config(Path(__file__).parent.parent / "config.toml")
    command_agents = agents_for_screen(config, "command")
    assert len(command_agents) == 6
    assert command_agents[0]["name"] == "adama"


def test_agents_sorted_by_slot():
    config = load_config(Path(__file__).parent.parent / "config.toml")
    media_agents = agents_for_screen(config, "media")
    slots = [a["slot"] for a in media_agents]
    assert slots == sorted(slots)
```

**Step 2: Run tests to verify they fail**

```bash
cd ~/Projects/leegonzales/dev-environment
python3 -m pytest fleet-up/tests/test_config.py -v
```

Expected: `ModuleNotFoundError` — fleet_up doesn't exist yet.

**Step 3: Write minimal implementation**

Create `fleet-up/fleet_up.py`:

```python
#!/usr/bin/env python3
"""fleet-up: Agent fleet launcher for Ghostty + tmux + AeroSpace."""

import argparse
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.toml"
CLAUDE_FLAGS = "--permission-mode bypassPermissions"


# ── Config ───────────────────────────────────────────


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load and return the fleet config."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def agents_for_screen(config: dict, screen: str) -> list[dict]:
    """Return agents assigned to a screen, sorted by slot."""
    return sorted(
        [a for a in config["agents"] if a["screen"] == screen],
        key=lambda a: a["slot"],
    )


def all_screens(config: dict) -> list[str]:
    """Return ordered list of screen names."""
    return list(config["screens"].keys())


# ── Display Detection ────────────────────────────────


def detect_display_mode(override: str | None = None) -> str:
    """Detect samsung vs macbook display mode.

    Uses system_profiler to check for external displays.
    Override with explicit mode string.
    """
    if override:
        return override

    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        data = json.loads(result.stdout)
        displays = []
        for gpu in data.get("SPDisplaysDataType", []):
            displays.extend(gpu.get("spdisplays_ndrvs", []))

        # If any display has resolution >= 3840 wide, assume Samsung
        for d in displays:
            res = d.get("_spdisplays_resolution", "")
            if "3840" in res or "2160" in res:
                return "samsung"

        # If more than 1 display, assume external = samsung
        if len(displays) > 1:
            return "samsung"

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        pass

    return "macbook"


# ── Workspace mapping ────────────────────────────────


def workspace_for_agent(config: dict, agent: dict, mode: str) -> int:
    """Return the AeroSpace workspace number for an agent."""
    screen_config = config["screens"][agent["screen"]]

    if mode == "samsung":
        return screen_config["workspace_samsung"]

    # MacBook: screens span multiple workspaces
    ws_list = screen_config["workspace_macbook"]
    if isinstance(ws_list, int):
        return ws_list

    grid = config["display"]["macbook"]
    slots_per_ws = grid["cols"] * grid["rows"]
    ws_index = (agent["slot"] - 1) // slots_per_ws
    ws_index = min(ws_index, len(ws_list) - 1)
    return ws_list[ws_index]


# ── tmux ─────────────────────────────────────────────


def tmux_session_exists(name: str) -> bool:
    """Check if a tmux session already exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def create_tmux_session(agent: dict) -> bool:
    """Create a detached tmux session for an agent.

    Returns True if created, False if already existed.
    """
    name = agent["name"]
    if tmux_session_exists(name):
        print(f"  tmux '{name}' exists, reusing")
        return False

    repo = os.path.expanduser(agent["repo"])
    if not os.path.isdir(repo):
        print(f"  WARNING: repo not found: {repo}, skipping {name}")
        return False

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-c", repo],
        check=True,
    )
    # Set window title
    subprocess.run(
        ["tmux", "rename-window", "-t", name, agent["label"]],
        check=True,
    )

    return True


def launch_in_tmux(agent: dict) -> None:
    """Send the launch command to a tmux session."""
    name = agent["name"]
    command = agent.get("command")

    if command:
        # Custom command (e.g., cass monitor)
        cmd = command
    elif agent.get("claude", False):
        cmd = f"claude {CLAUDE_FLAGS}"
    else:
        return  # workbench — just a shell

    # Check if something is already running (beyond the shell)
    result = subprocess.run(
        ["tmux", "list-panes", "-t", name, "-F", "#{pane_current_command}"],
        capture_output=True,
        text=True,
    )
    current = result.stdout.strip()
    if current and current not in ("zsh", "bash", "fish"):
        print(f"  {name}: process already running ({current}), skipping launch")
        return

    subprocess.run(
        ["tmux", "send-keys", "-t", name, cmd, "Enter"],
        check=True,
    )


# ── Ghostty ──────────────────────────────────────────


def open_ghostty_window(agent: dict) -> int | None:
    """Open a new Ghostty window attached to the agent's tmux session.

    Returns the PID of the Ghostty process, or None on failure.
    """
    name = agent["name"]
    label = agent["label"]

    # Ghostty CLI: open new window with tmux attach command
    # --title sets the window title
    # -e sets the command to run
    result = subprocess.Popen(
        [
            "open",
            "-na",
            "Ghostty",
            "--args",
            "-e",
            f"tmux attach-session -t {name}",
            "--title",
            label,
        ],
    )
    return result.pid


# ── AeroSpace ────────────────────────────────────────


def ensure_aerospace_running() -> bool:
    """Make sure AeroSpace is running. Start if needed."""
    result = subprocess.run(
        ["pgrep", "-x", "AeroSpace"],
        capture_output=True,
    )
    if result.returncode != 0:
        print("Starting AeroSpace...")
        subprocess.Popen(["open", "-a", "AeroSpace"])
        time.sleep(2)
    return True


def move_window_to_workspace(workspace: int, app_name: str = "Ghostty") -> None:
    """Move the most recently focused window to a workspace.

    AeroSpace CLI: aerospace move-node-to-workspace <ws>
    """
    subprocess.run(
        ["aerospace", "move-node-to-workspace", str(workspace)],
        capture_output=True,
    )


def list_aerospace_windows() -> list[dict]:
    """List all windows known to AeroSpace."""
    result = subprocess.run(
        ["aerospace", "list-windows", "--all", "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    return []


# ── Orchestrator ─────────────────────────────────────


def launch_agent(config: dict, agent: dict, mode: str) -> None:
    """Full launch sequence for a single agent."""
    name = agent["name"]
    label = agent["label"]
    ws = workspace_for_agent(config, agent, mode)
    print(f"[ws:{ws}] {label}")

    # 1. tmux session
    created = create_tmux_session(agent)

    # 2. Ghostty window
    open_ghostty_window(agent)
    time.sleep(0.5)  # let window open

    # 3. Move to workspace
    move_window_to_workspace(ws)
    time.sleep(0.2)

    # 4. Launch claude or custom command
    if created:
        launch_in_tmux(agent)


def launch_screen(config: dict, screen: str, mode: str) -> None:
    """Launch all agents for a screen."""
    agents = agents_for_screen(config, screen)
    print(f"\n{'='*40}")
    print(f"Screen: {config['screens'][screen]['label']}")
    print(f"{'='*40}")
    for agent in agents:
        launch_agent(config, agent, mode)


def launch_fleet(config: dict, mode: str, screen_filter: str | None = None,
                 agent_filter: str | None = None) -> None:
    """Launch the full fleet or a subset."""
    ensure_aerospace_running()

    if agent_filter:
        agents = [a for a in config["agents"] if a["name"] == agent_filter]
        if not agents:
            print(f"Unknown agent: {agent_filter}")
            sys.exit(1)
        launch_agent(config, agents[0], mode)
        return

    screens = [screen_filter] if screen_filter else all_screens(config)
    for screen in screens:
        if screen not in config["screens"]:
            print(f"Unknown screen: {screen}")
            sys.exit(1)
        launch_screen(config, screen, mode)


def show_status(config: dict) -> None:
    """Show what's currently running."""
    print(f"{'Agent':<20} {'tmux':<8} {'Screen':<15} {'Repo'}")
    print("-" * 70)
    for agent in config["agents"]:
        exists = tmux_session_exists(agent["name"])
        status = "UP" if exists else "DOWN"
        repo = agent["repo"].replace(os.path.expanduser("~"), "~")
        print(f"{agent['label']:<20} {status:<8} {agent['screen']:<15} {repo}")


def teardown(config: dict, screen_filter: str | None = None) -> None:
    """Kill tmux sessions and close Ghostty windows."""
    agents = config["agents"]
    if screen_filter:
        agents = agents_for_screen(config, screen_filter)

    for agent in agents:
        name = agent["name"]
        if tmux_session_exists(name):
            subprocess.run(["tmux", "kill-session", "-t", name], check=True)
            print(f"  killed {name}")


# ── CLI ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="fleet-up: Launch the agent fleet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fleet-up                        # Full fleet, auto-detect display
  fleet-up --mode samsung         # Force Samsung mode
  fleet-up --screen command       # Launch command screen only
  fleet-up --agent adama          # Launch single agent
  fleet-up --status               # Show fleet status
  fleet-up --down                 # Teardown everything
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["samsung", "macbook"],
        help="Display mode (auto-detected if omitted)",
    )
    parser.add_argument("--screen", help="Launch specific screen only")
    parser.add_argument("--agent", help="Launch specific agent only")
    parser.add_argument(
        "--status", action="store_true", help="Show fleet status"
    )
    parser.add_argument(
        "--down", action="store_true", help="Teardown fleet"
    )

    args = parser.parse_args()
    config = load_config()
    mode = detect_display_mode(override=args.mode)

    if args.status:
        show_status(config)
        return

    if args.down:
        teardown(config, screen_filter=args.screen)
        return

    print(f"fleet-up | mode: {mode}")
    launch_fleet(config, mode, screen_filter=args.screen, agent_filter=args.agent)
    print("\nFleet launched. Use 'fleet-up --status' to check.")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

```bash
cd ~/Projects/leegonzales/dev-environment
python3 -m pytest fleet-up/tests/test_config.py -v
```

Expected: 4 tests PASS.

**Step 5: Commit**

```bash
git add fleet-up/fleet_up.py fleet-up/tests/
git commit -m "feat: fleet-up config loader, display detection, and launcher"
```

---

### Task 3: AeroSpace config generation

**Files:**
- Create: `fleet-up/aerospace_config.py`
- Create: `fleet-up/tests/test_aerospace.py`

**Step 1: Write the failing test**

Create `fleet-up/tests/test_aerospace.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aerospace_config import generate_aerospace_toml


def test_generate_has_workspaces():
    toml_str = generate_aerospace_toml(num_workspaces=4, gap=8)
    assert "alt-1 = 'workspace 1'" in toml_str
    assert "alt-4 = 'workspace 4'" in toml_str


def test_generate_has_gaps():
    toml_str = generate_aerospace_toml(num_workspaces=4, gap=8)
    assert "inner.horizontal = 8" in toml_str


def test_generate_has_move_bindings():
    toml_str = generate_aerospace_toml(num_workspaces=4, gap=8)
    assert "alt-shift-1 = 'move-node-to-workspace 1'" in toml_str
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest fleet-up/tests/test_aerospace.py -v
```

Expected: FAIL.

**Step 3: Write implementation**

Create `fleet-up/aerospace_config.py`:

```python
"""Generate AeroSpace TOML config for fleet-up workspaces."""

from pathlib import Path

AEROSPACE_CONFIG_PATH = Path.home() / ".aerospace.toml"


def generate_aerospace_toml(num_workspaces: int = 4, gap: int = 8) -> str:
    """Generate an AeroSpace config with fleet-up workspaces."""
    lines = [
        "# Generated by fleet-up — do not edit manually",
        "# Regenerate with: fleet-up --gen-aerospace",
        "",
        "after-login-command = []",
        "after-startup-command = []",
        "start-at-login = true",
        "",
        "[gaps]",
        f"inner.horizontal = {gap}",
        f"inner.vertical = {gap}",
        f"outer.left = {gap}",
        f"outer.right = {gap}",
        f"outer.top = {gap}",
        f"outer.bottom = {gap}",
        "",
        "[mode.main.binding]",
    ]

    # Workspace focus: alt-N
    for i in range(1, num_workspaces + 1):
        lines.append(f"alt-{i} = 'workspace {i}'")

    lines.append("")

    # Move to workspace: alt-shift-N
    for i in range(1, num_workspaces + 1):
        lines.append(f"alt-shift-{i} = 'move-node-to-workspace {i}'")

    lines.append("")

    # Navigation
    lines.extend([
        "# Focus navigation",
        "alt-h = 'focus left'",
        "alt-j = 'focus down'",
        "alt-k = 'focus up'",
        "alt-l = 'focus right'",
        "",
        "# Move windows",
        "alt-shift-h = 'move left'",
        "alt-shift-j = 'move down'",
        "alt-shift-k = 'move up'",
        "alt-shift-l = 'move right'",
        "",
        "# Layout",
        "alt-slash = 'layout tiles horizontal vertical'",
        "alt-comma = 'layout accordion horizontal vertical'",
        "alt-f = 'fullscreen'",
        "",
        "# Resize",
        "alt-shift-minus = 'resize smart -50'",
        "alt-shift-equal = 'resize smart +50'",
    ])

    return "\n".join(lines) + "\n"


def write_aerospace_config(num_workspaces: int = 4, gap: int = 8,
                           path: Path = AEROSPACE_CONFIG_PATH) -> Path:
    """Write AeroSpace config to disk. Returns the path written."""
    content = generate_aerospace_toml(num_workspaces, gap)
    path.write_text(content)
    return path
```

**Step 4: Run tests**

```bash
python3 -m pytest fleet-up/tests/test_aerospace.py -v
```

Expected: 3 PASS.

**Step 5: Commit**

```bash
git add fleet-up/aerospace_config.py fleet-up/tests/test_aerospace.py
git commit -m "feat: AeroSpace config generator with workspace bindings"
```

---

### Task 4: CLI entry point and `fleet-up` symlink

**Files:**
- Create: `fleet-up/__main__.py`
- Modify: `fleet-up/fleet_up.py` (add shebang, make executable)

**Step 1: Create entry point**

Create `fleet-up/__main__.py`:

```python
"""Allow `python3 -m fleet-up` invocation."""
from fleet_up import main

main()
```

**Step 2: Make fleet_up.py executable**

```bash
chmod +x ~/Projects/leegonzales/dev-environment/fleet-up/fleet_up.py
```

**Step 3: Create symlink in ~/bin**

```bash
mkdir -p ~/bin
ln -sf ~/Projects/leegonzales/dev-environment/fleet-up/fleet_up.py ~/bin/fleet-up
```

Verify `~/bin` is on PATH (should be via zshrc). Test:

```bash
fleet-up --help
```

Expected: Prints usage with examples.

**Step 4: Commit**

```bash
git add fleet-up/__main__.py fleet-up/fleet_up.py
git commit -m "feat: CLI entry point and fleet-up symlink"
```

---

### Task 5: Integration test — launch 2 agents, verify, teardown

**Files:**
- Create: `fleet-up/tests/test_integration.py`

**Step 1: Write the integration test**

```python
"""Integration test: launch 2 agents, verify tmux, teardown.

Requires tmux running. Skipped in CI.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fleet_up import (
    create_tmux_session,
    launch_in_tmux,
    load_config,
    teardown,
    tmux_session_exists,
)

# Only run locally
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Requires tmux + display",
)


@pytest.fixture
def config():
    return load_config()


def test_tmux_session_lifecycle(config):
    """Create a tmux session, verify it exists, kill it."""
    agent = {
        "name": "test-agent",
        "label": "Test Agent",
        "repo": "~/Projects",
        "claude": False,
    }

    # Cleanup in case prior run left it
    if tmux_session_exists("test-agent"):
        subprocess.run(["tmux", "kill-session", "-t", "test-agent"])

    # Create
    created = create_tmux_session(agent)
    assert created is True
    assert tmux_session_exists("test-agent")

    # Idempotent: second call doesn't create
    created2 = create_tmux_session(agent)
    assert created2 is False

    # Cleanup
    subprocess.run(["tmux", "kill-session", "-t", "test-agent"])
    assert not tmux_session_exists("test-agent")


def test_status_runs(config):
    """fleet-up --status should not crash."""
    result = subprocess.run(
        [sys.executable, "-m", "fleet_up", "--status"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    # May exit 0 or show DOWN agents — just shouldn't crash
    assert "Agent" in result.stdout or result.returncode == 0
```

**Step 2: Run integration tests**

```bash
python3 -m pytest fleet-up/tests/test_integration.py -v
```

Expected: 2 PASS (creates a test tmux session, verifies lifecycle, tears down).

**Step 3: Commit**

```bash
git add fleet-up/tests/test_integration.py
git commit -m "test: integration test for tmux session lifecycle"
```

---

### Task 6: Manual smoke test on Samsung display

This is a manual verification task. No code to write.

**Step 1: Ensure AeroSpace is running and configured**

```bash
fleet-up --gen-aerospace  # if implemented, or manually copy aerospace.toml
aerospace reload-config
```

**Step 2: Launch command screen only**

```bash
fleet-up --mode samsung --screen command
```

Verify:
- [ ] 6 Ghostty windows open
- [ ] Each has correct title (Adama, Dax-1, Dax-2, Alfred-1, Alfred-2, cass monitor)
- [ ] All are on workspace 1
- [ ] AeroSpace tiles them in 3x2 grid
- [ ] Claude is running in agent sessions (not in cass-monitor or workbench)
- [ ] Claude launched with `--permission-mode bypassPermissions`

**Step 3: Check status**

```bash
fleet-up --status
```

Verify: All 6 command agents show "UP".

**Step 4: Teardown**

```bash
fleet-up --down --screen command
```

Verify: tmux sessions killed, Ghostty windows closed.

**Step 5: Full fleet launch**

```bash
fleet-up --mode samsung
```

Verify:
- [ ] 4 workspaces populated
- [ ] Alt+1 through Alt+4 switches between them
- [ ] ~22 agents visible across workspaces
- [ ] Labels readable, layout makes sense

---

### Task 7: MacBook mode reflow test

**Step 1: Launch in MacBook mode**

```bash
fleet-up --down  # clean slate
fleet-up --mode macbook
```

Verify:
- [ ] 6 workspaces (instead of 4)
- [ ] 4 terminals per workspace (2x2 grid)
- [ ] Only 1 cass-monitor (not per-screen)
- [ ] Same agents, just reflowed

---

### Summary: Task dependency graph

```
Task 1 (scaffold + config)
  └─→ Task 2 (config loader + fleet_up.py)
       ├─→ Task 3 (aerospace config gen)
       │    └─→ Task 6 (Samsung smoke test)
       │         └─→ Task 7 (MacBook smoke test)
       └─→ Task 4 (CLI entry point)
            └─→ Task 5 (integration tests)
```

Tasks 3 and 4 can run in parallel after Task 2.
Tasks 6 and 7 are manual and sequential.
