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
