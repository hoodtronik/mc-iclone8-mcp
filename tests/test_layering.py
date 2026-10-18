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


def _flat_hand(side):
    """T-pose hand, palm down: right hand reaches -X, left +X; index toward -Y (the front), pinky +Y."""
    sx = -1.0 if side == "R" else 1.0
    p = f"CC_Base_{side}_"
    ident = (0.0, 0.0, 0.0, 1.0)
    bind = {p + "Hand": ((sx * 70.0, 0.0, 150.0), ident)}
    for f, y in (("Thumb", -4.0), ("Index", -3.0), ("Mid", -1.0), ("Ring", 1.0), ("Pinky", 3.0)):
        for k in (1, 2, 3):
            bind[p + f + str(k)] = ((sx * (78.0 + 3.0 * k), y, 150.0), ident)
    return bind


def test_finger_curl_bends_toward_the_palm_on_both_hands():
    from tools.seating import qrot
    for side in ("R", "L"):
        t = L.finger_targets(_flat_hand(side), side, "fist")
        bone_dir = (-1.0 if side == "R" else 1.0, 0.0, 0.0)            # fingers point away from the body
        q = t[f"CC_Base_{side}_Index2"]
        d = qrot(q, bone_dir)
        assert d[2] < -0.9, (side, d)                                  # 95 deg curl: now points down, into the palm


def test_point_keeps_the_index_straight():
    t = L.finger_targets(_flat_hand("R"), "R", "point")
    assert L.angle_deg(t["CC_Base_R_Index2"], (0.0, 0.0, 0.0, 1.0)) < 1e-6
    assert L.angle_deg(t["CC_Base_R_Mid2"], (0.0, 0.0, 0.0, 1.0)) > 90


def test_body_rotation_axes_follow_the_facing():
    from tools.seating import qrot
    fwd = (0.0, -1.0)                                            # facing -Y; the character's right is -X
    q = L.body_rotation(fwd, yaw=90)
    d = qrot(q, (0.0, -1.0, 0.0))
    assert abs(d[0] - 1.0) < 1e-9                                # yaw +90: now faces +X (its left, like `turn`)
    q = L.body_rotation(fwd, pitch=30)
    d = qrot(q, (0.0, -1.0, 0.0))
    assert d[2] > 0.49                                           # pitch +: the face tips up
    q = L.body_rotation(fwd, roll=20)
    u = qrot(q, (0.0, 0.0, 1.0))
    assert u[0] < -0.3                                           # roll +: the top leans to the right (-X)
    q = L.body_rotation((1.0, 0.0), pitch=30)                   # same pitch on a body facing +X tips toward +Z too
    assert qrot(q, (1.0, 0.0, 0.0))[2] > 0.49
