"""Offline tests for tools.vehicles.key_plan."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import vehicles as V  # noqa: E402


def test_constant_speed_keys():
    plan = V.key_plan(2400.0, 800.0, 30.0, 30)      # 3 s drive starting at frame 30
    assert plan[0] == (30, 0.0) and plan[-1] == (120, 100.0)
    assert len(plan) == 4                            # one key per second
    steps = [b[0] - a[0] for a, b in zip(plan, plan[1:])]
    assert max(steps) - min(steps) <= 1


def test_short_drive_still_two_segments():
    plan = V.key_plan(100.0, 800.0, 30.0, 0)
    assert len(plan) == 3 and plan[-1][1] == 100.0
