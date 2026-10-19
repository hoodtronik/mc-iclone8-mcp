import math

from tools.ik_pose import slerp, new_layer, key_bones, lerp3
from tools.seating import qmul


def _close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b)) or all(abs(x + y) < tol for x, y in zip(a, b))


def test_new_layer_turns_the_composed_local_into_the_target():
    clip = (0.0, 0.0, math.sin(0.2), math.cos(0.2))
    old = (math.sin(0.1), 0.0, 0.0, math.cos(0.1))
    composed = qmul(old, clip)
    target = (0.0, math.sin(0.3), 0.0, math.cos(0.3))
    lay = new_layer(target, composed, old)
    assert _close(qmul(lay, clip), target)


def test_slerp_ends_and_middle():
    a, b = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, math.sin(0.5), math.cos(0.5))
    assert _close(slerp(a, b, 0.0), a) and _close(slerp(a, b, 1.0), b)
    assert _close(slerp(a, b, 0.5), (0.0, 0.0, math.sin(0.25), math.cos(0.25)))


def test_lerp3():
    assert lerp3((0, 0, 0), (10, 20, 30), 0.5) == (5, 10, 15)


class _B:
    def __init__(self, name, parent=None):
        self.n, self.p = name, parent

    def GetName(self):
        return self.n

    def GetParent(self):
        return self.p


def test_key_bones_body_takes_the_chain_to_the_hip_and_the_legs_not_the_other_arm():
    hip = _B("CC_Base_Hip", _B("RL_BoneRoot"))
    hand = _B("CC_Base_R_Hand", _B("CC_Base_R_Forearm", _B("CC_Base_R_Upperarm", _B("CC_Base_R_Clavicle",
              _B("CC_Base_Spine02", _B("CC_Base_Spine01", _B("CC_Base_Waist", hip)))))))
    ks = key_bones("right_hand", hand, True)
    assert {"CC_Base_Spine02", "CC_Base_Waist", "CC_Base_Hip", "CC_Base_L_Foot", "CC_Base_R_Thigh"} <= ks
    assert "CC_Base_L_Hand" not in ks and "CC_Base_Head" not in ks and "RL_BoneRoot" not in ks
    assert key_bones("right_hand", hand, False) == {"CC_Base_R_Clavicle", "CC_Base_R_Upperarm", "CC_Base_R_Forearm",
                                                     "CC_Base_R_Hand"}


def test_same_hemisphere_keeps_consecutive_keys_on_one_side():
    from tools.ik_pose import same_hemisphere
    q = (0.0, 0.0, 0.1, -0.995)
    assert same_hemisphere(q, None) == q
    assert same_hemisphere(q, (0.0, 0.0, 0.0, 1.0)) == (-0.0, -0.0, -0.1, 0.995)
    assert same_hemisphere(q, (0.0, 0.0, 0.0, -1.0)) == q


def test_spec_ik_is_checked():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import spec_check
    spec = {"length_s": 8, "set": [{"name": "Box", "size": [20, 20, 20], "at": [0, 0]}],
            "cast": [{"name": "A", "avatar": "x", "ik": [
                {"effector": "left_hand", "object": "Box", "at_s": 1, "hold_s": 2},
                {"effector": "tail", "point": [0, 0, 1]},
                {"effector": "head"},
                {"effector": "right_foot", "object": "Nope"}]}]}
    errs, _ = spec_check.check(spec, ".")
    e = " | ".join(x for x in errs if "ik[" in x)
    assert "ik[0]" not in e and "ik[1]" in e and "ik[2]" in e and "ik[3]" in e
