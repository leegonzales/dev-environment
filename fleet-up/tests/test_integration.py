"""Integration test: tmux session lifecycle.

Requires tmux running. Skipped in CI.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fleet_up import (
    load_config,
    tmux_session_exists,
    create_screen_session,
    agents_for_screen,
    _pane_count,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Requires tmux + display",
)


@pytest.fixture(autouse=True)
def cleanup_test_session():
    """Ensure test tmux sessions are cleaned up."""
    yield
    for name in ("test-screen", "command"):
        if tmux_session_exists(name):
            subprocess.run(["tmux", "kill-session", "-t", name], check=False)


def test_screen_session_lifecycle():
    """Create a screen session with panes, verify, tear down."""
    config = load_config()

    # Clean slate
    if tmux_session_exists("command"):
        subprocess.run(["tmux", "kill-session", "-t", "command"], check=False)

    # Create command screen session
    created = create_screen_session(config, "command", "samsung")
    assert created is True
    assert tmux_session_exists("command")

    # Should have 6 panes (6 agents on command screen)
    assert _pane_count("command") == 6

    # Idempotent: second call returns False
    created2 = create_screen_session(config, "command", "samsung")
    assert created2 is False

    # Teardown
    subprocess.run(["tmux", "kill-session", "-t", "command"], check=False)
    assert not tmux_session_exists("command")


def test_status_command():
    """fleet-up --status should not crash."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "fleet_up.py"), "--status"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Command" in result.stdout
