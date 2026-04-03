#!/usr/bin/env python3
"""fleet-up: Launch agent fleet in Ghostty + tmux. No third-party WM needed.

Architecture:
  - 4 tmux sessions (command, training, media, tools)
  - Each session has panes tiled in a grid, one per agent
  - 4 Ghostty windows, one per session
  - You full-screen each Ghostty window → 4 macOS Spaces

Dependencies: tmux (already installed), Ghostty (already installed), Python 3.11+
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

CLAUDE_FLAGS = "--permission-mode bypassPermissions"
CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"

# Pane border format using @agent_label (survives Claude overwriting pane_title)
TMUX_PANE_BORDER = "#{?pane_active,#[bold],#[dim]}#{@agent_label}"


# ── Config ──────────────────────────────────────────────


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
    """Detect samsung (external 42") vs macbook (built-in 14").

    Samsung: 6 panes per session (3x2 grid)
    MacBook: 4 panes per session (2x2 grid), overflow agents get own sessions
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


# ── tmux helpers ────────────────────────────────────────


def tmux_session_exists(name: str) -> bool:
    """Check if a tmux session with the given name exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def _pane_count(session: str) -> int:
    """Return number of panes in a tmux session."""
    result = subprocess.run(
        ["tmux", "list-panes", "-t", session],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    return len(result.stdout.strip().splitlines())


def _base_indices(session: str) -> tuple[int, int]:
    """Get window base-index and pane base-index for a session."""
    result = subprocess.run(
        ["tmux", "show-options", "-gv", "base-index"],
        capture_output=True, text=True,
    )
    win_base = int(result.stdout.strip()) if result.returncode == 0 else 0

    result = subprocess.run(
        ["tmux", "show-options", "-gv", "pane-base-index"],
        capture_output=True, text=True,
    )
    pane_base = int(result.stdout.strip()) if result.returncode == 0 else 0

    return win_base, pane_base


def _pane_target(session: str, pane_index: int) -> str:
    """Build a tmux pane target that works regardless of base-index."""
    win_base, pane_base = _base_indices(session)
    return f"{session}:{win_base}.{pane_base + pane_index}"


def _pane_running(session: str, pane_index: int) -> bool:
    """Check if something other than a shell is running in a specific pane."""
    target = _pane_target(session, pane_index)
    result = subprocess.run(
        ["tmux", "display-message", "-t", target, "-p", "#{pane_current_command}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    cmd = result.stdout.strip()
    return cmd not in ("", "zsh", "bash", "sh", "fish")


# ── tmux session builder ───────────────────────────────


def create_screen_session(
    config: dict, screen: str, mode: str,
) -> bool:
    """Create a tmux session for a screen with one pane per agent.

    Returns True if created, False if already existed.
    """
    session_name = screen
    agents = agents_for_screen(config, screen)

    if not agents:
        print(f"  No agents for screen '{screen}', skipping")
        return False

    if tmux_session_exists(session_name):
        return False

    # Create session with first agent's repo
    first_repo = str(Path(agents[0]["repo"]).expanduser())
    if not Path(first_repo).is_dir():
        first_repo = str(Path.home())

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, "-c", first_repo],
        check=True,
    )

    # Label the first pane (using @agent_label — survives Claude overwriting pane_title)
    subprocess.run(
        ["tmux", "set-option", "-t", _pane_target(session_name, 0),
         "-p", "@agent_label", agents[0].get("label", agents[0]["name"])],
        check=False,
    )

    # Create additional panes for remaining agents
    for i, agent in enumerate(agents[1:], start=1):
        repo = str(Path(agent["repo"]).expanduser())
        if not Path(repo).is_dir():
            repo = str(Path.home())

        subprocess.run(
            ["tmux", "split-window", "-t", session_name, "-c", repo],
            check=True,
        )
        subprocess.run(
            ["tmux", "set-option", "-t", _pane_target(session_name, i),
             "-p", "@agent_label", agent.get("label", agent["name"])],
            check=False,
        )

        # Re-tile after each split to keep things balanced
        subprocess.run(
            ["tmux", "select-layout", "-t", session_name, "tiled"],
            check=False,
        )

    # Enable pane border labels
    subprocess.run(
        ["tmux", "set-option", "-t", session_name,
         "pane-border-status", "top"],
        check=False,
    )
    subprocess.run(
        ["tmux", "set-option", "-t", session_name,
         "pane-border-format", TMUX_PANE_BORDER],
        check=False,
    )

    # Final tiled layout
    subprocess.run(
        ["tmux", "select-layout", "-t", session_name, "tiled"],
        check=False,
    )

    return True


def launch_agents_in_session(
    config: dict, screen: str,
) -> None:
    """Send launch commands to each pane in a screen session."""
    session_name = screen
    agents = agents_for_screen(config, screen)

    for i, agent in enumerate(agents):
        target = _pane_target(session_name, i)

        if _pane_running(session_name, i):
            print(f"    {agent['name']}: process running, skipping")
            continue

        if agent.get("claude", False):
            cmd = f"claude {CLAUDE_FLAGS}"
        elif agent.get("command"):
            cmd = agent["command"]
        else:
            continue  # workbench — just a shell

        subprocess.run(
            ["tmux", "send-keys", "-t", target, cmd, "Enter"],
            check=True,
        )
        print(f"    {agent['name']}: launched")
        time.sleep(0.3)  # Brief pause between launches


# ── Ghostty ─────────────────────────────────────────────


def _client_attached_to(session: str) -> bool:
    """Check if any tmux client is attached to this session."""
    result = subprocess.run(
        ["tmux", "list-clients", "-t", session, "-F", "#{client_name}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def open_ghostty_for_session(session: str, label: str) -> None:
    """Open a Ghostty window attached to a tmux session.

    Skips if a client is already attached.
    Title is set via tmux (Ghostty's -e consumes all remaining args).
    """
    if _client_attached_to(session):
        print(f"  Ghostty already attached to '{session}', skipping")
        return

    # Set tmux session name as window title (Ghostty picks this up)
    subprocess.run(
        ["tmux", "rename-window", "-t", session, label],
        check=False,
    )

    subprocess.Popen(
        [
            "open", "-na", "Ghostty", "--args",
            "-e", f"tmux attach-session -t {session}",
        ],
    )


# ── Orchestration ──────────────────────────────────────


def launch_screen(config: dict, screen: str, mode: str) -> None:
    """Launch a screen: create tmux session with panes, open Ghostty."""
    screen_cfg = config["screens"][screen]
    agents = agents_for_screen(config, screen)
    label = screen_cfg["label"]

    print(f"\n{'='*50}")
    print(f"Screen: {label} ({len(agents)} agents)")
    print(f"{'='*50}")

    created = create_screen_session(config, screen, mode)
    if created:
        print(f"  Created tmux session '{screen}' with {len(agents)} panes")
        launch_agents_in_session(config, screen)
    else:
        print(f"  tmux session '{screen}' exists, checking agents...")
        launch_agents_in_session(config, screen)

    # Open Ghostty window
    open_ghostty_for_session(screen, label)
    time.sleep(0.5)


def launch_fleet(
    config: dict,
    mode: str,
    screen_filter: str | None = None,
) -> None:
    """Main orchestrator: launch the full fleet or a single screen."""
    print(f"fleet-up | mode={mode} | tmux-only (no WM dependencies)")

    screens = [screen_filter] if screen_filter else all_screens(config)
    for screen in screens:
        if screen not in config["screens"]:
            print(f"ERROR: screen '{screen}' not found in config")
            sys.exit(1)
        launch_screen(config, screen, mode)

    print(f"\nFleet launched. Full-screen each Ghostty window (Cmd+Ctrl+F) for separate Spaces.")
    print(f"Use 'fleet-up --status' to check agent status.")


# ── Status ─────────────────────────────────────────────


def show_status(config: dict) -> None:
    """Print status of all screens and their agents."""
    for screen in all_screens(config):
        screen_cfg = config["screens"][screen]
        agents = agents_for_screen(config, screen)
        session_up = tmux_session_exists(screen)
        client = _client_attached_to(screen) if session_up else False

        print(f"\n  {screen_cfg['label']}  tmux={'UP' if session_up else 'DOWN'}  "
              f"ghostty={'attached' if client else 'none'}")
        print(f"  {'-'*45}")

        for i, agent in enumerate(agents):
            running = _pane_running(screen, i) if session_up else False
            status = "RUNNING" if running else ("idle" if session_up else "down")
            print(f"    {agent['label']:<30} {status}")


# ── Teardown ───────────────────────────────────────────


def teardown(config: dict, screen_filter: str | None = None) -> None:
    """Kill tmux sessions."""
    screens = [screen_filter] if screen_filter else all_screens(config)

    for screen in screens:
        if tmux_session_exists(screen):
            subprocess.run(["tmux", "kill-session", "-t", screen], check=False)
            print(f"  Killed session: {screen}")
        else:
            print(f"  No session: {screen}")


# ── CLI ────────────────────────────────────────────────


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="fleet-up: Launch agent fleet in Ghostty + tmux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  fleet-up                        # Full fleet, auto-detect display
  fleet-up --mode samsung         # Force Samsung 42" mode
  fleet-up --mode macbook         # Force MacBook 14" mode
  fleet-up --screen command       # Launch command screen only
  fleet-up --status               # Show fleet status
  fleet-up --down                 # Teardown everything
  fleet-up --down --screen media  # Teardown media screen only

After launch, full-screen each Ghostty window (Cmd+Ctrl+F) to create
separate macOS Spaces. Swipe between them with trackpad or Ctrl+arrows.
        """,
    )
    parser.add_argument(
        "--mode", choices=["samsung", "macbook"], default=None,
        help="Display mode (auto-detects if omitted)",
    )
    parser.add_argument(
        "--screen", default=None,
        help="Launch/teardown specific screen only",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show fleet status",
    )
    parser.add_argument(
        "--down", action="store_true",
        help="Tear down (kill) tmux sessions",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.toml",
    )

    args = parser.parse_args()

    config_path = Path(args.config) if args.config else CONFIG_PATH
    config = load_config(config_path)

    if args.status:
        show_status(config)
        return

    mode = detect_display_mode(override=args.mode)

    if args.down:
        teardown(config, screen_filter=args.screen)
        return

    launch_fleet(config, mode, screen_filter=args.screen)


if __name__ == "__main__":
    main()
