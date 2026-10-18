"""Offline tests for tools.scene.moved_pose (clone offset/turn)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402

_install_fakes([], {})
import RLPy  # noqa: E402  (the fake)
for _n in ("Object", "Avatar", "Prop", "Camera", "Light", "Particle"):
    setattr(RLPy, "EObjectType_" + _n, 0)
from tools.scene import moved_pose  # noqa: E402


def test_offset_only_keeps_rotation():
    p, q = moved_pose((10, 20, 5), (0, 0, 0, 1), (10, 20, 5), (100, 0, 0), 0)
    assert p == (110, 20, 5) and q == (0, 0, 0, 1)


def test_turn_about_pivot_rotates_position_and_heading():
    p, q = moved_pose((100, 0, 0), (0, 0, 0, 1), (0, 0, 0), (0, 0, 0), 90)
    assert abs(p[0]) < 1e-9 and abs(p[1] - 100) < 1e-9
    s = math.sqrt(0.5)
    assert abs(q[2] - s) < 1e-9 and abs(q[3] - s) < 1e-9


def test_turns_compose():
    _, q1 = moved_pose((0, 0, 0), (0, 0, 0, 1), (0, 0, 0), (0, 0, 0), 30)
    _, q2 = moved_pose((0, 0, 0), q1, (0, 0, 0), (0, 0, 0), 60)
    s = math.sqrt(0.5)
    assert abs(q2[2] - s) < 1e-9 and abs(q2[3] - s) < 1e-9
