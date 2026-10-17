"""Offline tests for tools.groups.ring (layout math)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import groups as G  # noqa: E402


def _front(hd):
    a = math.radians(hd)
    return (math.sin(a), -math.cos(a))          # CC front (-Y) rotated by heading about Z


def test_two_people_face_each_other_110_cm_apart():
    (x0, y0, h0), (x1, y1, h1) = G.ring(2)
    assert abs(math.hypot(x1 - x0, y1 - y0) - 110.0) < 1e-6
    f0 = _front(h0)
    assert f0[0] * (x1 - x0) + f0[1] * (y1 - y0) > 109.9      # member 0 faces member 1


def test_ring_members_face_the_centre():
    for x, y, hd in G.ring(3, center=(100.0, 50.0)):
        fx, fy = _front(hd)
        cx, cy = 100.0 - x, 50.0 - y
        assert abs(fx * cx + fy * cy - math.hypot(cx, cy)) < 1e-6


def test_member_zero_on_camera_side():
    x, y, _ = G.ring(3, start_deg=0.0)[0]
    assert abs(x) < 1e-9 and y < 0
