"""Offline tests for tools.interactions geometry."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import interactions as I  # noqa: E402


def test_meet_points_midway_offset_toward_each_person():
    pa, pb, d = I.meet_points((0.0, 0.0, 140.0), (80.0, 0.0, 140.0), 100.0, 96.0)
    assert d == 80.0
    assert pa == (37.0, 0.0, 116.0) and pb == (43.0, 0.0, 116.0)


def test_shake_keys_start_and_end_at_rest():
    k = I.shake_keys(2.0, 2.0)
    assert k[0] == (2.0, 0.0) and k[-1] == (4.0, 0.0)
    assert any(dz > 0 for _, dz in k) and any(dz < 0 for _, dz in k)
