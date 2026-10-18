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


def test_wipe_keys_stroke_across_and_return():
    from tools.interactions import wipe_keys
    k = wipe_keys((0.0, 0.0, 100.0), (1.0, 0.0), 2.0, 2.0, width_cm=40.0, stroke_s=0.6)
    assert k[0] == (2.0, (0.0, 0.0, 100.0)) and k[-1] == (4.0, (0.0, 0.0, 100.0))
    xs = [p[0] for _, p in k[1:-1]]
    assert xs[0] == 20.0 and xs[1] == -20.0 and all(p[2] == 100.0 for _, p in k)


def test_axis_angle_and_laugh_envelope():
    assert abs(L.angle_deg(L.axis_angle((0, 0, 2), 30), _qz(30))) < 1e-6
    a = L.laugh_angles(0.0, 1.0)
    assert a["CC_Base_Head"] > a["CC_Base_Spine02"] > 0          # leans back, head most
    assert all(v == 0 for v in L.laugh_angles(0.3, 0.0).values())  # nothing outside the envelope
