"""Offline tests for tools.lighting.sun_direction."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import lighting as Lt  # noqa: E402


def test_sun_from_plus_x_low_shines_toward_minus_x_and_down():
    d = Lt.sun_direction(90.0, 20.0)
    assert d[0] < -0.9 and abs(d[1]) < 1e-9 and d[2] < 0


def test_sun_behind_camera_shines_toward_plus_y():
    d = Lt.sun_direction(0.0, 45.0)
    assert abs(d[0]) < 1e-9 and d[1] > 0.7 and abs(d[2] + math.sqrt(0.5)) < 1e-9
