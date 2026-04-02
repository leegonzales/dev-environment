import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fleet_up import load_config, detect_display_mode, agents_for_screen, all_screens


def test_load_config_returns_agents():
    config = load_config()
    assert len(config["agents"]) == 22
    assert config["display"]["samsung"]["cols"] == 3


def test_detect_display_mode_override():
    assert detect_display_mode(override="samsung") == "samsung"
    assert detect_display_mode(override="macbook") == "macbook"


def test_agents_for_screen():
    config = load_config()
    command_agents = agents_for_screen(config, "command")
    assert len(command_agents) == 6
    assert command_agents[0]["name"] == "adama"


def test_agents_sorted_by_slot():
    config = load_config()
    media_agents = agents_for_screen(config, "media")
    slots = [a["slot"] for a in media_agents]
    assert slots == sorted(slots)


def test_all_screens_order():
    config = load_config()
    screens = all_screens(config)
    assert screens == ["command", "training", "media", "tools"]


def test_screen_agent_counts():
    config = load_config()
    assert len(agents_for_screen(config, "command")) == 6
    assert len(agents_for_screen(config, "training")) == 5
    assert len(agents_for_screen(config, "media")) == 6
    assert len(agents_for_screen(config, "tools")) == 5
