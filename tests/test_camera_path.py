"""Offline tests for tools.camera_path curve helpers."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.camera_path import curve_points, ease, orbit_points  # noqa: E402


def test_curve_passes_through_ends_and_spaces_evenly():
    pts, length = curve_points([[0, 0, 0], [100, 0, 0], [200, 0, 0]], 5)
    assert abs(length - 200) < 1e-6
    assert [round(p[0], 6) for p in pts] == [0, 50, 100, 150, 200]


def test_curve_bends_through_a_middle_point():
    pts, _ = curve_points([[0, 0, 0], [100, 100, 0], [200, 0, 0]], 41)
    assert min(math.dist(p, (100, 100, 0)) for p in pts) < 3.0
    gaps = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    assert max(gaps) - min(gaps) < 0.5                       # constant speed along the arc


def test_orbit_azimuth_convention():
    a, b = orbit_points([0, 0], 100, 0, 90, 150, n=2)
    assert abs(a[0]) < 1e-9 and abs(a[1] + 100) < 1e-9       # 0 deg = -Y side
    assert abs(b[0] - 100) < 1e-9 and abs(b[1]) < 1e-9        # +90 = counter-clockwise -> +X
    assert a[2] == 150


def test_ease_is_soft_at_both_ends():
    assert ease(0, "ease") == 0 and ease(1, "ease") == 1 and ease(0.5, "ease") == 0.5
    assert ease(0.1, "ease") < 0.1 and ease(0.9, "ease") > 0.9
    assert ease(0.3, "linear") == 0.3
