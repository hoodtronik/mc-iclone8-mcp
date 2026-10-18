"""Offline tests for doorway rooms (scripts/build_scene.py room_walls / swing_keys)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_scene as B  # noqa: E402


def test_doorway_splits_its_wall_into_sides_and_lintel():
    walls = B.room_walls("Cafe", 700, 600, 300, [0, 0], [{"wall": "-X", "center": -150, "width": 110, "height": 220}])
    west = [w for w in walls if "Wall-X" in w["name"]]
    assert len(west) == 3 and len(walls) == 6
    lintel = next(w for w in west if w["bottom_z"] == 220)
    assert lintel["size"] == [10.0, 110.0, 80.0] and lintel["at"] == [-355.0, -150.0]
    sides = sorted((w for w in west if w["bottom_z"] == 0), key=lambda w: w["at"][1])
    assert math.isclose(sides[0]["at"][1] + sides[0]["size"][1] / 2, -205.0)     # opening from -205 ...
    assert math.isclose(sides[1]["at"][1] - sides[1]["size"][1] / 2, -95.0)      # ... to -95


def test_swing_follows_the_hinge_arc():
    keys = B.swing_keys((0.0, 0.0), (0.0, 50.0), -90.0, 4)
    assert keys[0][1] == (0.0, 50.0)
    x, y = keys[-1][1]
    assert math.isclose(x, 50.0, abs_tol=1e-9) and math.isclose(y, 0.0, abs_tol=1e-9)   # (0,1) turned -90 -> (+1,0)
    assert all(math.isclose(math.hypot(*p), 50.0) for _, p, _ in keys)             # stays on the arc
