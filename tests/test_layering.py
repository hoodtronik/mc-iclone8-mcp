"""Offline tests for tools/layering.py pure helpers."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import layering as L  # noqa: E402
from tools.seating import qmul  # noqa: E402


def _qz(deg):
    h = math.radians(deg) / 2
    return (0.0, 0.0, math.sin(h), math.cos(h))


def test_full_offset_turns_base_into_target():
    base, target = _qz(30), _qz(100)
    off = L.layer_offset(target, base)
    assert L.angle_deg(qmul(off, base), target) < 1e-6      # layer * clip, as measured live


def test_half_weight_is_half_the_rotation():
    off = L.layer_offset(_qz(90), _qz(0), 0.5)
    assert abs(L.angle_deg(off, (0, 0, 0, 1)) - 45.0) < 1e-6


def test_ramp_blends_in_and_out():
    assert L.ramp(100, 100, 200, 12) == 0.0
    assert L.ramp(150, 100, 200, 12) == 1.0
    assert 0.0 < L.ramp(106, 100, 200, 12) < 1.0
    assert L.ramp(200, 100, 200, 12) == 0.0
