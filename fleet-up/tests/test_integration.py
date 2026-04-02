"""Integration test: launch 2 agents, verify tmux, teardown.

Requires tmux running. Skipped in CI.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fleet_up import (
    create_tmux_session,
    load_config,
    tmux_session_exists,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Requires tmux + display",
)


@pytest.fixture(autouse=True)
def cleanup_test_session():
    """Ensure test tmux session is cleaned up."""
    yield
    if tmux_session_exists("test-agent"):
        subprocess.run(["tmux", "kill-session", "-t", "test-agent"], check=False)


def test_tmux_session_lifecycle():
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

    # Idempotent: second call returns False
    created2 = create_tmux_session(agent)
    assert created2 is False

    # Cleanup
    subprocess.run(["tmux", "kill-session", "-t", "test-agent"])
    assert not tmux_session_exists("test-agent")


def test_status_command():
    """fleet-up --status should not crash."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "fleet_up.py"), "--status"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Name" in result.stdout  # Header row
