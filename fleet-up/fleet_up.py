#!/usr/bin/env python3
"""fleet-up: Launch and manage a fleet of Claude Code agents across screens."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

CLAUDE_FLAGS = "--permission-mode bypassPermissions"


# ── Config ──────────────────────────────────────────────


CONFIG_PATH = Path(__file__).parent / "config.toml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load TOML config and return parsed dict."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def agents_for_screen(config: dict, screen: str) -> list[dict]:
    """Return agents for a given screen, sorted by slot."""
    return sorted(
        [a for a in config["agents"] if a["screen"] == screen],
        key=lambda a: a["slot"],
    )


def all_screens(config: dict) -> list[str]:
    """Return ordered list of screen names."""
    return list(config["screens"].keys())


# ── Display Detection ───────────────────────────────────


def detect_display_mode(override: str | None = None) -> str:
    """Detect whether we're on a Samsung (external) or MacBook display.

    Rules:
    - --mode flag overrides everything
    - If any display has 3840 or 2160 in resolution → samsung
    - If more than 1 display → samsung
    - Otherwise → macbook
    """
    if override:
        return override

    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return "macbook"

    displays: list[dict] = []
    for gpu in data.get("SPDisplaysDataType", []):
        for display in gpu.get("spdisplays_ndrvs", []):
            displays.append(display)

    if len(displays) > 1:
        return "samsung"

    for display in displays:
        res = display.get("_spdisplays_resolution", "")
        if "3840" in res or "2160" in res:
            return "samsung"

    return "macbook"


# ── Workspace Mapping ───────────────────────────────────


def workspace_for_agent(config: dict, agent: dict, mode: str) -> int:
    """Map an agent to an AeroSpace workspace number.

    Samsung: each screen gets one workspace.
    MacBook: screens split across multiple workspaces based on slot count.
    """
    screen_cfg = config["screens"][agent["screen"]]
    ws = screen_cfg[f"workspace_{mode}"]

    if isinstance(ws, int):
        return ws

    # MacBook: list of workspaces — distribute agents across them
    display_cfg = config["display"][mode]
    slots_per_ws = display_cfg["cols"] * display_cfg["rows"]
    screen_agents = agents_for_screen(config, agent["screen"])

    for i, a in enumerate(screen_agents):
        if a["name"] == agent["name"]:
            ws_index = min(i // slots_per_ws, len(ws) - 1)
            return ws[ws_index]

    return ws[0]


# ── tmux ────────────────────────────────────────────────


def tmux_session_exists(name: str) -> bool:
    """Check if a tmux session with the given name exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def _process_running_in_tmux(name: str) -> bool:
    """Check if something other than a shell is running in the tmux session."""
    result = subprocess.run(
        ["tmux", "list-panes", "-t", name, "-F", "#{pane_current_command}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    cmd = result.stdout.strip()
    return cmd not in ("", "zsh", "bash", "sh", "fish")


def create_tmux_session(agent: dict) -> bool:
    """Create a detached tmux session, cd to repo, set title.

    Returns True if created, False if already existed.
    """
    name = agent["name"]
    if tmux_session_exists(name):
        return False

    repo = str(Path(agent["repo"]).expanduser())

    if not Path(repo).is_dir():
        print(f"  WARN: repo {repo} does not exist, using $HOME")
        repo = str(Path.home())

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-c", repo],
        check=True,
    )
    # Set pane title
    subprocess.run(
        ["tmux", "select-pane", "-t", name, "-T", agent.get("label", name)],
        check=False,
    )
    return True


def launch_in_tmux(agent: dict) -> None:
    """Send the launch command to the tmux session."""
    name = agent["name"]

    if agent.get("claude", False):
        cmd = f"claude {CLAUDE_FLAGS}"
    elif agent.get("command"):
        cmd = agent["command"]
    else:
        # No command, just leave the shell open
        return

    subprocess.run(
        ["tmux", "send-keys", "-t", name, cmd, "Enter"],
        check=True,
    )


# ── Ghostty ─────────────────────────────────────────────


def _ghostty_window_exists_for(name: str) -> bool:
    """Check if a Ghostty window is already attached to this tmux session."""
    result = subprocess.run(
        ["tmux", "list-clients", "-t", name, "-F", "#{client_name}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def open_ghostty_window(agent: dict) -> None:
    """Open a Ghostty window attached to the agent's tmux session.

    Skips if a client is already attached to the tmux session.
    """
    name = agent["name"]
    label = agent.get("label", name)

    if _ghostty_window_exists_for(name):
        print(f"    Ghostty already attached to '{name}', skipping")
        return

    subprocess.Popen(
        [
            "open", "-na", "Ghostty", "--args",
            "-e", f"tmux attach-session -t {name}",
            "--title", label,
        ],
    )


# ── AeroSpace ──────────────────────────────────────────


def ensure_aerospace_running() -> None:
    """Start AeroSpace if it's not already running."""
    result = subprocess.run(
        ["pgrep", "-x", "AeroSpace"],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.Popen(["open", "-a", "AeroSpace"])
        time.sleep(2)  # Give it a moment to start


def move_window_to_workspace(workspace: int) -> None:
    """Move the focused window to an AeroSpace workspace."""
    subprocess.run(
        ["aerospace", "move-node-to-workspace", str(workspace)],
        check=False,
    )


# ── Orchestration ──────────────────────────────────────


def launch_agent(config: dict, agent: dict, mode: str) -> None:
    """Full launch sequence for one agent."""
    name = agent["name"]
    print(f"  Launching {name} ({agent.get('label', name)})...")

    # 1. tmux session (idempotent)
    repo_path = Path(agent["repo"]).expanduser()
    if not repo_path.is_dir():
        print(f"    WARN: repo {repo_path} missing, skipping agent")
        return

    created = create_tmux_session(agent)
    if created:
        launch_in_tmux(agent)
    elif not _process_running_in_tmux(name):
        print(f"    tmux session '{name}' exists, relaunching command")
        launch_in_tmux(agent)
    else:
        print(f"    tmux session '{name}' exists, process running, skipping")

    # 2. Ghostty window (idempotent — skips if already attached)
    already_attached = _ghostty_window_exists_for(name)
    if not already_attached:
        open_ghostty_window(agent)
        time.sleep(0.5)  # Let window open and register with AeroSpace

        # 3. Move new window to workspace
        ws = workspace_for_agent(config, agent, mode)
        move_window_to_workspace(ws)


def launch_screen(config: dict, screen: str, mode: str) -> None:
    """Launch all agents for a screen."""
    agents = agents_for_screen(config, screen)
    print(f"\n{'='*50}")
    print(f"Screen: {config['screens'][screen]['label']} ({len(agents)} agents)")
    print(f"{'='*50}")

    for agent in agents:
        launch_agent(config, agent, mode)


def launch_fleet(
    config: dict,
    mode: str,
    screen_filter: str | None = None,
    agent_filter: str | None = None,
) -> None:
    """Main orchestrator: launch the full fleet or a subset."""
    print(f"Fleet-Up | mode={mode}")

    ensure_aerospace_running()

    if agent_filter:
        # Launch a single agent by name
        for agent in config["agents"]:
            if agent["name"] == agent_filter:
                launch_agent(config, agent, mode)
                return
        print(f"ERROR: agent '{agent_filter}' not found in config")
        sys.exit(1)

    screens = [screen_filter] if screen_filter else all_screens(config)
    for screen in screens:
        if screen not in config["screens"]:
            print(f"ERROR: screen '{screen}' not found in config")
            sys.exit(1)
        launch_screen(config, screen, mode)

    print(f"\nFleet-Up complete. {len(config['agents'])} agents configured.")


# ── Status ─────────────────────────────────────────────


def show_status(config: dict) -> None:
    """Print a table of agent status (tmux session alive or not)."""
    print(f"{'Name':<15} {'Screen':<12} {'Slot':<5} {'tmux':<8} {'Running':<8}")
    print("-" * 55)

    for agent in config["agents"]:
        name = agent["name"]
        exists = tmux_session_exists(name)
        running = _process_running_in_tmux(name) if exists else False
        print(
            f"{name:<15} {agent['screen']:<12} {agent['slot']:<5} "
            f"{'YES' if exists else '-':<8} {'YES' if running else '-':<8}"
        )


# ── Teardown ───────────────────────────────────────────


def teardown(config: dict, screen_filter: str | None = None) -> None:
    """Kill tmux sessions for agents."""
    agents = config["agents"]
    if screen_filter:
        agents = [a for a in agents if a["screen"] == screen_filter]

    for agent in agents:
        name = agent["name"]
        if tmux_session_exists(name):
            subprocess.run(["tmux", "kill-session", "-t", name], check=False)
            print(f"  Killed tmux session: {name}")
        else:
            print(f"  No session: {name}")


# ── CLI ────────────────────────────────────────────────


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Launch and manage a fleet of Claude Code agents."
    )
    parser.add_argument(
        "--mode",
        choices=["samsung", "macbook"],
        default=None,
        help="Display mode override (auto-detects if omitted)",
    )
    parser.add_argument(
        "--screen",
        default=None,
        help="Launch only agents for this screen",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="Launch only this specific agent",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all agents",
    )
    parser.add_argument(
        "--down",
        action="store_true",
        help="Tear down (kill) tmux sessions",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.toml (default: alongside this script)",
    )

    args = parser.parse_args()

    config_path = Path(args.config) if args.config else Path(__file__).parent / "config.toml"
    config = load_config(config_path)

    if args.status:
        show_status(config)
        return

    mode = detect_display_mode(override=args.mode)

    if args.down:
        teardown(config, screen_filter=args.screen)
        return

    launch_fleet(config, mode, screen_filter=args.screen, agent_filter=args.agent)


if __name__ == "__main__":
    main()
