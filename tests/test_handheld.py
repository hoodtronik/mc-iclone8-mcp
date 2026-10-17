"""Offline tests for tools.handheld pose math."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import handheld as H  # noqa: E402
from tools import seating as S  # noqa: E402


def test_euler_identity_and_z90():
    assert all(abs(a - b) < 1e-9 for a, b in zip(H.euler_q((0, 0, 0)), (0, 0, 0, 1)))
    v = S.qrot(H.euler_q((0, 0, 90)), (1.0, 0.0, 0.0))
    assert abs(v[0]) < 1e-9 and abs(v[1] - 1.0) < 1e-9


def test_hold_pose_offset_follows_hand_rotation():
    h = math.sqrt(0.5)
    hand_q = (0.0, 0.0, h, h)                       # hand turned 90 deg about Z
    T, Q = H.hold_pose((10.0, 0.0, 100.0), hand_q, (0.0, 9.0, 0.0))
    assert abs(T[0] - 1.0) < 1e-9 and abs(T[1]) < 1e-9 and T[2] == 100.0   # +Y of the hand now points -X
    assert all(abs(a - b) < 1e-9 for a, b in zip(Q, hand_q))
